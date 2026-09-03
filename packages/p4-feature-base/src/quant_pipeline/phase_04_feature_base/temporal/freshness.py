from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from ..models import ExecutionContext
from ..runtime.canonical import canonical_json
from ..runtime.schema_validation import validate_json_schema
from .errors import TemporalContractError, TemporalErrorCode
from .materialization import capability_records
from .output import build_s2_artifact
from .policy import policy_for


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _quality_state(payload: Mapping[str, Any]) -> str:
    for field in ("quality_status", "source_quality_status", "quality_flag", "status"):
        value = payload.get(field)
        if value in (None, ""):
            continue
        normalized = str(value).upper()
        if normalized in {"BLOCK", "BLOCKED", "FAILED", "REJECTED"}:
            return "BLOCKED"
        if normalized in {"WARN", "WARNING", "DEGRADED"}:
            return "DEGRADED"
    return "VALIDATED"


def _revision_key(record: Mapping[str, Any]) -> tuple[str, ...]:
    artifact_name = str(record["source_artifact_name"])
    policy = policy_for(artifact_name)
    payload = record.get("payload", {})
    if not isinstance(payload, Mapping) or not policy.revision_key_fields:
        return artifact_name, str(record["source_record_id"])
    values = [artifact_name, str(record["entity_id"])]
    for field in policy.revision_key_fields:
        value = record.get("reference_time") if field == "reference_time" else payload.get(field)
        values.append(str(value or ""))
    return tuple(values)


def _resolve_tie(
    tied: list[Mapping[str, Any]], key: tuple[str, ...]
) -> Mapping[str, Any]:
    sequences = [row.get("stable_sequence") for row in tied]
    stable = all(value not in (None, "") for value in sequences)
    unique = len(set(map(str, sequences))) == len(tied)
    if not stable or not unique:
        payloads = {canonical_json(row.get("payload", {})) for row in tied}
        if len(payloads) > 1:
            raise TemporalContractError(
                TemporalErrorCode.REVISION_TIE,
                "conflicting revisions share available_at without a stable sequence",
                path="revision_selection",
                details={"revision_key": key},
            )
    ordered = sorted(
        tied,
        key=lambda row: (
            str(row.get("stable_sequence") or ""),
            str(row["source_record_id"]),
        ),
    )
    return ordered[-1]


def _chosen_revision(
    group: list[Mapping[str, Any]], key: tuple[str, ...]
) -> Mapping[str, Any]:
    policy = policy_for(str(group[0]["source_artifact_name"]))
    if len(group) == 1 or not policy.revision_key_fields:
        return group[0]
    ordered = sorted(
        group,
        key=lambda row: (
            str(row["available_at"]),
            str(row.get("stable_sequence") or ""),
            str(row["source_record_id"]),
        ),
    )
    latest_time = ordered[-1]["available_at"]
    tied = [row for row in ordered if row["available_at"] == latest_time]
    return tied[-1] if len(tied) == 1 else _resolve_tie(tied, key)


def _select_revisions(
    records: list[Mapping[str, Any]],
) -> tuple[set[str], list[dict[str, Any]]]:
    groups: dict[tuple[str, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        groups[_revision_key(record)].append(record)
    selected: set[str] = set()
    report: list[dict[str, Any]] = []
    for key, group in sorted(groups.items(), key=lambda item: item[0]):
        chosen_id = str(_chosen_revision(group, key)["source_record_id"])
        selected.add(chosen_id)
        for row in group:
            report.append(
                {
                    "revision_key": list(key),
                    "source_record_id": str(row["source_record_id"]),
                    "available_at": str(row["available_at"]),
                    "vintage_id": row.get("vintage_id"),
                    "selected": str(row["source_record_id"]) == chosen_id,
                }
            )
    return selected, report


def _validated_records(
    inputs: Mapping[str, Any], input_schema: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    required = (
        "entity_aligned_observation_bundle",
        "phase2_capability_matrix",
        "phase3_capability_matrix",
    )
    missing = [name for name in required if name not in inputs]
    if missing:
        raise TemporalContractError(
            TemporalErrorCode.INPUT_MISSING, f"missing inputs: {missing}", path="inputs"
        )
    bundle = inputs["entity_aligned_observation_bundle"]
    if not isinstance(bundle, Mapping):
        raise TemporalContractError(
            TemporalErrorCode.INPUT_INVALID, "bundle must be a mapping"
        )
    try:
        validate_json_schema(bundle, input_schema, "entity_aligned_observation_bundle")
    except Exception as exc:
        raise TemporalContractError(
            TemporalErrorCode.SCHEMA_INVALID,
            str(exc),
            path="entity_aligned_observation_bundle",
        ) from exc
    records = bundle.get("records", [])
    assert isinstance(records, list)
    return records


def _freshness_state(
    record: Mapping[str, Any],
    context: ExecutionContext,
    selected: set[str],
    thresholds: Mapping[str, Any],
) -> tuple[float, float | None, str, str, bool]:
    available_at = _parse_utc(str(record["available_at"]))
    record_decision = _parse_utc(str(record.get("decision_time") or context.decision_time.isoformat()))
    age = max(0.0, (record_decision - available_at).total_seconds())
    threshold_value = thresholds.get(str(record["source_modality"]))
    threshold = float(threshold_value) if threshold_value is not None else None
    payload = record.get("payload", {})
    assert isinstance(payload, Mapping)
    quality = _quality_state(payload)
    is_selected = str(record["source_record_id"]) in selected
    if quality == "BLOCKED":
        state = "QUALITY_BLOCKED"
    elif not is_selected:
        state = "REVISED_SUPERSEDED"
    elif threshold is not None and age > threshold:
        state = "STALE"
    else:
        state = "OBSERVED"
    return age, threshold, quality, state, is_selected


def _enrich_records(
    records: list[Mapping[str, Any]],
    context: ExecutionContext,
    selected: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_thresholds = context.config.get("freshness_threshold_seconds_by_modality", {})
    thresholds = raw_thresholds if isinstance(raw_thresholds, Mapping) else {}
    enriched: list[dict[str, Any]] = []
    missingness: list[dict[str, Any]] = []
    for record in records:
        age, threshold, quality, state, is_selected = _freshness_state(
            record, context, selected, thresholds
        )
        enriched.append(
            {
                **dict(record),
                "freshness_seconds": age,
                "freshness_threshold_seconds": threshold,
                "quality_state": quality,
                "missingness_state": state,
                "selected_vintage": is_selected,
                "revision_status": "SELECTED" if is_selected else "SUPERSEDED",
            }
        )
        missingness.append(
            {
                "scope": "SOURCE_RECORD",
                "artifact_name": str(record["source_artifact_name"]),
                "source_record_id": str(record["source_record_id"]),
                "entity_id": str(record["entity_id"]),
                "state": state,
                "reason": None,
                "freshness_seconds": age,
            }
        )
    return enriched, missingness


def _append_unavailable_capabilities(
    inputs: Mapping[str, Any], missingness: list[dict[str, Any]]
) -> None:
    for capability in capability_records(inputs):
        if str(capability.get("status")) == "AVAILABLE":
            continue
        name = capability.get("artifact_name") or capability.get("capability")
        missingness.append(
            {
                "scope": "CAPABILITY",
                "artifact_name": str(name),
                "source_record_id": None,
                "entity_id": None,
                "state": "UNAVAILABLE_UPSTREAM",
                "reason": capability.get("reason"),
                "freshness_seconds": None,
            }
        )


def _sort_outputs(
    enriched: list[dict[str, Any]],
    missingness: list[dict[str, Any]],
    revisions: list[dict[str, Any]],
) -> None:
    enriched.sort(
        key=lambda row: (row["entity_id"], row["available_at"], row["source_record_id"])
    )
    missingness.sort(
        key=lambda row: (
            row["scope"],
            row["artifact_name"],
            str(row.get("source_record_id")),
        )
    )
    revisions.sort(
        key=lambda row: (
            tuple(row["revision_key"]),
            row["available_at"],
            row["source_record_id"],
        )
    )


def map_freshness_and_missingness(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
    *,
    input_schema: Mapping[str, Any],
    s2_schemas: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    records = _validated_records(inputs, input_schema)
    selected, revision_report = _select_revisions(records)
    enriched, missingness = _enrich_records(records, context, selected)
    _append_unavailable_capabilities(inputs, missingness)
    _sort_outputs(enriched, missingness, revision_report)
    artifacts = {
        "quality_enriched_observation_bundle": build_s2_artifact(
            name="quality_enriched_observation_bundle",
            module_id="P4.S2.M03",
            context=context,
            records=enriched,
            schema=s2_schemas["quality_enriched_observation_bundle"],
            extra={"revision_policy": "latest_available_vintage_at_cutoff"},
        ),
        "availability_missingness_panel": build_s2_artifact(
            name="availability_missingness_panel",
            module_id="P4.S2.M03",
            context=context,
            records=missingness,
            schema=s2_schemas["availability_missingness_panel"],
        ),
        "revision_selection_report": build_s2_artifact(
            name="revision_selection_report",
            module_id="P4.S2.M03",
            context=context,
            records=revision_report,
            schema=s2_schemas["revision_selection_report"],
        ),
    }
    return artifacts
