"""P4 V14.9 research-lineage and receipt helpers."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..boundary.p4_v149 import P4BoundaryCatalog, P4_VERSION, canonical_sha256
from ..errors import ContractError, DataQualityError, ReasonCode
from .horizon_policy import passport_target_scope, policy_version
from .identifiers import as_utc, stable_id


def plain_records(value: Any, name: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, dict) or not isinstance(value.get("records"), list):
        raise DataQualityError(f"{name} must contain records")
    records = value["records"]
    if any(not isinstance(row, dict) for row in records):
        raise DataQualityError(f"{name} records must be objects")
    return list(records)


def normalize_passports(
    passport_artifact: dict[str, Any] | None,
    budget_artifact: dict[str, Any] | None,
    attempt_artifact: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    passports = plain_records(passport_artifact, "approved_hypothesis_passport_registry")
    budgets = _budget_map(plain_records(budget_artifact, "hypothesis_budget_report"))
    attempts = plain_records(attempt_artifact, "research_attempt_ledger")
    attempt_count = _attempt_counts(attempts)
    records = [
        _normalize_passport(row, passport_artifact, budgets, attempt_count)
        for row in passports
        if str(row.get("status")) in {"FOUNDATIONAL", "APPROVED"}
    ]
    ids = [row["hypothesis_id"] for row in records]
    if len(ids) != len(set(ids)):
        raise DataQualityError("P4 hypothesis IDs must be unique")
    lineage = {
        "p4_passport_artifact_id": None if passport_artifact is None else passport_artifact.get("artifact_id"),
        "p4_budget_artifact_id": None if budget_artifact is None else budget_artifact.get("artifact_id"),
        "p4_attempt_artifact_id": None if attempt_artifact is None else attempt_artifact.get("artifact_id"),
        "horizon_binding_policy": policy_version(),
        "attempt_record_count": len(attempts),
    }
    return records, lineage


def _attempt_counts(attempts: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in attempts:
        identifier = str(row.get("hypothesis_id") or "").strip()
        if identifier:
            counts[identifier] = counts.get(identifier, 0) + 1
    return counts


def _normalize_passport(
    row: dict[str, Any],
    passport_artifact: dict[str, Any] | None,
    budgets: dict[str, dict[str, Any]],
    attempt_count: dict[str, int],
) -> dict[str, Any]:
    hypothesis_id = str(row.get("hypothesis_id") or "").strip()
    family_id = str(row.get("family_id") or "").strip()
    primary_horizon = str(row.get("primary_horizon") or "").strip().upper()
    if not hypothesis_id or not family_id or not primary_horizon:
        raise DataQualityError("P4 passport lacks hypothesis_id/family_id/primary_horizon")
    if hypothesis_id not in budgets:
        raise DataQualityError(f"P4 passport {hypothesis_id} lacks budget record")
    targets, horizons = passport_target_scope(primary_horizon)
    budget = budgets[hypothesis_id]
    return {
        "hypothesis_id": hypothesis_id,
        "passport_version": _passport_version(passport_artifact, row),
        "status": "APPROVED",
        "family_id": family_id,
        "hypothesis_name": str(row.get("hypothesis_name") or hypothesis_id),
        "mechanism": str(row.get("mechanism") or ""),
        "expected_sign": str(row.get("expected_sign") or "CONTEXT_DEPENDENT"),
        "falsification_rule": str(row.get("falsification_rule") or ""),
        "primary_horizon_group": primary_horizon,
        "allowed_targets": targets,
        "allowed_horizons": horizons,
        "horizon_binding_policy": policy_version(),
        "p4_parameterization_limit": budget["limit"],
        "p4_approved_parameterizations": budget["approved_count"],
        "p4_budget_status": budget["status"],
        "p4_attempt_events": attempt_count.get(hypothesis_id, 0),
        "remaining_budget": max(0, budget["limit"] - budget["approved_count"]),
        "budget_exhausted": budget["approved_count"] >= budget["limit"],
        "allowed_model_families": list(row.get("allowed_model_families", [])),
        "allowed_view_ids": list(row.get("allowed_view_ids", [])),
        "max_attempts": budget["max_attempts"],
        "max_configurations": budget["max_configurations"],
        "max_seconds": budget["max_seconds"],
        "max_memory_mb": budget["max_memory_mb"],
        "policy_version": "P5-RC34-RESEARCH-BUDGET-V2",
    }


def normalize_conflicts(value: dict[str, Any] | None) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in plain_records(value, "perspective_conflict_panel"):
        entity = str(row.get("entity_id") or row.get("underlying") or "").strip()
        decision_time = row.get("decision_time") or row.get("as_of_time")
        group_id = str(row.get("group_id") or "").strip()
        horizon_group = str(row.get("horizon_group") or "").strip()
        if not entity or decision_time is None or not group_id or not horizon_group:
            raise DataQualityError("P4 conflict row lacks entity/time/group/horizon")
        key = (entity, as_utc(decision_time).isoformat(), group_id, horizon_group)
        if key in seen:
            raise DataQualityError(f"duplicate P4 perspective conflict key: {key}")
        seen.add(key)
        metrics = {
            name: _bounded_optional(row.get(name), name)
            for name in ("conflict_score", "consensus_score", "entropy_score", "minority_view_strength")
        }
        dispersion = row.get("dispersion_score")
        if dispersion is not None and float(dispersion) < 0:
            raise DataQualityError("P4 conflict dispersion_score must be nonnegative")
        available_at = str(row.get("available_at") or "").strip()
        if not available_at:
            raise DataQualityError(
                "P4 conflict row lacks explicit available_at",
                reason_code=ReasonCode.FUTURE_INFORMATION,
            )
        if as_utc(available_at) > as_utc(decision_time):
            raise DataQualityError(
                "P4 conflict row is future-available",
                reason_code=ReasonCode.FUTURE_INFORMATION,
            )
        output.append({
            "underlying": entity,
            "decision_time": key[1],
            "available_at": available_at,
            "group_id": group_id,
            "horizon_group": horizon_group,
            **metrics,
            "dispersion_score": None if dispersion is None else float(dispersion),
            "quality_state": str(row.get("quality_state") or "PASS"),
            "missingness_state": str(row.get("missingness_state") or "OBSERVED"),
            "source_modalities": list(row.get("source_modalities", [])),
            "lineage_id": str(row.get("record_lineage_id") or row.get("lineage_id") or stable_id(key)),
        })
    return output


def build_consumption_receipt(
    catalog: P4BoundaryCatalog,
    *,
    run_id: str,
    cycle_id: str,
    as_of_time: datetime,
    created_at: datetime,
    view_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    accepted = sorted(str(row["artifact_id"]) for row in catalog.handoff.records)
    views = [] if view_registry is None else list(view_registry.get("views", []))
    record = {
        "handoff_manifest_id": catalog.handoff.artifact_id,
        "handoff_manifest_hash": catalog.handoff.content_hash,
        "consumer_phase": "phase_05_underlying_forecasts",
        "accepted_artifact_ids": accepted,
        "rejected_artifact_ids": [],
        "adaptations_applied": [],
        "received_at": as_utc(created_at).isoformat(),
        "materialized_view_ids": sorted(str(row.get("view_id")) for row in views),
        "materialized_view_hashes": {
            str(row.get("view_id")): str(row.get("materialized_view_hash")) for row in views
        },
        "included_feature_ids": sorted({
            str(feature) for row in views for feature in row.get("included_feature_ids", [])
        }),
        "excluded_feature_ids": sorted({
            str(feature) for row in views for feature in row.get("excluded_feature_ids", [])
        }),
        "view_quality_states": {
            str(row.get("view_id")): str(row.get("quality_state")) for row in views
        },
    }
    metadata = {
        "p4_contract_version": P4_VERSION,
        "native_boundary": True,
        "internal_projection_is_not_wire_adaptation": True,
    }
    payload_hash = canonical_sha256({"records": [record], "metadata": metadata, "alias_of": None})
    return {
        "artifact_id": f"phase5_consumption_receipt:{payload_hash[:16]}",
        "artifact_name": "phase5_consumption_receipt",
        "schema_version": P4_VERSION,
        "producer_phase": "phase_05_underlying_forecasts",
        "producer_module_id": "P5.S1.M05",
        "run_id": run_id,
        "cycle_id": cycle_id,
        "as_of_time": as_utc(as_of_time).isoformat(),
        "created_at": as_utc(created_at).isoformat(),
        "content_hash": payload_hash,
        "record_count": 1,
        "grain": ["handoff_manifest_id"],
        "lineage_id": stable_id("p4-v149-receipt", catalog.handoff.artifact_id, accepted),
        "execution_status": "PRODUCED",
        "quality_status": "VALIDATED",
        "records": [record],
        "metadata": metadata,
        "alias_of": None,
    }


def _budget_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        identifier = str(row.get("hypothesis_id") or "").strip()
        limit = int(row.get("limit", row.get("budget", 0)))
        approved = int(row.get("approved_count", 0))
        status = str(row.get("status") or "UNKNOWN")
        if not identifier or identifier in output or limit < 0 or approved < 0 or approved > limit:
            raise DataQualityError("P4 budget records require unique IDs and valid counts")
        output[identifier] = {
            "limit": limit, "approved_count": approved, "status": status,
            "max_attempts": int(row.get("max_attempts", max(limit, 1))),
            "max_configurations": int(row.get("max_configurations", max(limit, 1))),
            "max_seconds": int(row.get("max_seconds", 300)),
            "max_memory_mb": int(row.get("max_memory_mb", 1024)),
        }
    return output


def _passport_version(artifact: dict[str, Any] | None, row: dict[str, Any]) -> str:
    if artifact and artifact.get("schema_version"):
        return f"{artifact['schema_version']}:{str(artifact.get('content_hash', ''))[:12]}"
    return f"v14.9:{stable_id(row)[:12]}"


def _bounded_optional(value: Any, name: str) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise DataQualityError(f"P4 {name} must be between zero and one")
    return number
