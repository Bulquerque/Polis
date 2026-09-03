from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..artifact_protocol import lineage_hash, stable_hash
from ..economic_errors import ContractError
from ..economic_models import CanonicalObservationPanel, ExecutionContext, MissingnessState, QualityState
from .policy import LegacyAdapterPolicy


def _records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict) and isinstance(value.get("records"), list):
        return [dict(row) for row in value["records"]]
    if isinstance(value, list):
        return [dict(row) for row in value]
    raise ContractError("P4_S4_P3_ARTIFACT_INVALID", "P3 artifact must contain records")


def _time(value: Any, *, field_name: str, policy: LegacyAdapterPolicy, fallback: datetime) -> datetime:
    if value is None:
        if policy.allow_temporal_fallback:
            return fallback
        raise ContractError("P4_S4_P3_TIME_MISSING", f"missing required temporal field: {field_name}")
    text = str(value)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is not None and parsed.utcoffset() is not None:
        return parsed
    if len(text) == 10:
        return parsed.replace(tzinfo=timezone.utc)
    if policy.allow_naive_datetime_utc:
        return parsed.replace(tzinfo=timezone.utc)
    raise ContractError("P4_S4_P3_TIME_NAIVE", f"timezone required for field: {field_name}")


def _quality(value: Any) -> QualityState:
    text = str(value or "PASS").upper()
    if text in {"BLOCKED", "FAIL"}:
        return QualityState.BLOCKED
    return QualityState.DEGRADED if text not in {"PASS", "OK"} else QualityState.PASS


def _lineage(row: dict[str, Any], policy: LegacyAdapterPolicy) -> str:
    value = row.get("lineage_id")
    if value:
        return str(value)
    if policy.allow_generated_lineage:
        return f"p3-{stable_hash(row)[:20]}"
    raise ContractError("P4_S4_P3_LINEAGE_MISSING", "P3 record is missing lineage_id")


def _base(
    row: dict[str, Any],
    context: ExecutionContext,
    policy: LegacyAdapterPolicy,
    variable_id: str,
    value: Any,
    modality: str,
    attributes: dict[str, Any],
    entity_field: str = "underlying",
) -> dict[str, Any]:
    pit_status = str(row.get("pit_status") or "").upper()
    if pit_status in {"UNPROVEN", "DATE_LEVEL_PIT_UNPROVEN", "SNAPSHOT_ONLY", "SNAPSHOT_OR_DATE_LEVEL_ONLY"}:
        raise ContractError("P4_S4_P3_PIT_UNPROVEN", f"P3 record has unproven PIT status: {pit_status}")
    if row.get("timezone_assumed") or row.get("retrieved_timezone_assumed"):
        raise ContractError("P4_S4_P3_TIMEZONE_ASSUMED", "P3 record relies on an assumed timezone")
    available = _time(row.get("available_at"), field_name="available_at", policy=policy, fallback=context.as_of_time)
    decision = _time(
        row.get("as_of_time") or row.get("as_of_date") or row.get("date"),
        field_name="as_of_time/as_of_date/date",
        policy=policy,
        fallback=available,
    )
    aligned = decision < available
    quality = _quality(row.get("quality_status"))
    return {
        "decision_time": available if aligned else decision,
        "entity_id": str(row.get(entity_field) or "__GLOBAL__"),
        "variable_id": variable_id,
        "value": value,
        "source_modality": modality,
        "available_at": available,
        "quality_state": quality,
        "missingness_state": MissingnessState.QUALITY_BLOCKED if quality is QualityState.BLOCKED else MissingnessState.OBSERVED,
        "record_lineage_id": _lineage(row, policy),
        "source_id": row.get("source_id"),
        "unit": row.get("feature_type"),
        "attributes": {
            **attributes,
            "decision_aligned_to_available": aligned,
            "pit_status": row.get("pit_status"),
            "availability_basis": row.get("availability_basis"),
            "vintage_id": row.get("vintage_id") or row.get("revision_id"),
        },
    }


def _append_social(output: list[dict[str, Any]], rows: list[dict[str, Any]], context: ExecutionContext, policy: LegacyAdapterPolicy) -> None:
    for row in rows:
        output.append(
            _base(
                row,
                context,
                policy,
                f"social.feature.{row['feature_name']}",
                row["feature_value"],
                "social",
                {
                    "proposition_id": row.get("proposition_id"),
                    "horizon": row.get("horizon"),
                    "source_quality_score": row.get("source_quality_score"),
                },
            )
        )


def _append_evidence(output: list[dict[str, Any]], rows: list[dict[str, Any]], context: ExecutionContext, policy: LegacyAdapterPolicy) -> None:
    relation_score = {"SUPPORTS": 1.0, "OPPOSES": -1.0, "CONTEXT_ONLY": 0.0}
    for row in rows:
        relation = str(row.get("evidence_relation"))
        if relation not in relation_score:
            raise ContractError("P4_S4_P3_EVIDENCE_RELATION_INVALID", f"unsupported evidence relation: {relation}")
        output.append(
            _base(
                row,
                context,
                policy,
                "evidence.relation_score",
                relation_score[relation],
                "evidence",
                {
                    "proposition_id": row.get("proposition_id"),
                    "evidence_id": row.get("evidence_id"),
                    "source_quality_score": row.get("source_quality_score"),
                    "evidence_kind": row.get("evidence_kind"),
                },
            )
        )


def _append_disagreement(output: list[dict[str, Any]], rows: list[dict[str, Any]], context: ExecutionContext, policy: LegacyAdapterPolicy) -> None:
    fields = (
        "disagreement_score",
        "direction_disagreement_score",
        "confidence_disagreement_score",
        "evidence_disagreement_score",
        "polarization_score",
        "belief_variance_score",
    )
    for row in rows:
        for field in fields:
            if row.get(field) is not None:
                output.append(
                    _base(
                        row,
                        context,
                        policy,
                        f"agent.disagreement.{field}",
                        row[field],
                        "agent_disagreement",
                        {"proposition_id": row.get("proposition_id"), "horizon": row.get("horizon")},
                    )
                )


def _append_memory(output: list[dict[str, Any]], rows: list[dict[str, Any]], context: ExecutionContext, policy: LegacyAdapterPolicy) -> None:
    for row in rows:
        output.append(
            _base(
                row,
                context,
                policy,
                f"memory.feature.{row['feature_name']}",
                row["feature_value"],
                "context_memory",
                {"proposition_id": row.get("proposition_id"), "horizon": row.get("horizon")},
            )
        )


def _append_hypotheses(output: list[dict[str, Any]], rows: list[dict[str, Any]], context: ExecutionContext, policy: LegacyAdapterPolicy) -> None:
    for row in rows:
        output.append(
            _base(
                row,
                context,
                policy,
                "hypothesis.active",
                1.0,
                "hypothesis",
                {
                    "hypothesis_id": row.get("hypothesis_id"),
                    "proposition_id": row.get("proposition_id"),
                    "horizon": row.get("horizon"),
                    "matures_at": row.get("matures_at"),
                },
                entity_field="underlying_id",
            )
        )


def adapt_p3_artifacts(
    artifacts: dict[str, Any],
    context: ExecutionContext,
    *,
    policy: LegacyAdapterPolicy | None = None,
) -> CanonicalObservationPanel:
    active_policy = policy or LegacyAdapterPolicy()
    output: list[dict[str, Any]] = []
    _append_social(output, _records(artifacts.get("social_feature_panel")), context, active_policy)
    _append_evidence(output, _records(artifacts.get("evidence_tag_panel")), context, active_policy)
    _append_disagreement(output, _records(artifacts.get("agent_disagreement_panel")), context, active_policy)
    _append_memory(output, _records(artifacts.get("context_memory_feature_panel")), context, active_policy)
    _append_hypotheses(output, _records(artifacts.get("hypothesis_registry")), context, active_policy)
    return CanonicalObservationPanel.model_validate(
        {
            "artifact_id": f"canonical-p3:{stable_hash(output)[:16]}",
            "schema_version": "p4.canonical.v1",
            "pipeline_version": context.pipeline_version,
            "run_id": context.run_id,
            "cycle_id": context.cycle_id,
            "as_of_time": context.as_of_time,
            "created_at": context.created_at,
            "lineage_id": lineage_hash(row["record_lineage_id"] for row in output),
            "records": output,
        }
    )
