from __future__ import annotations
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from ...domain.canonical import digest, iso_utc, parse_utc
from ...domain.errors import fail
from .contracts import RuntimePolicy, artifact_map, REQUIRED_TOURNAMENT_ARTIFACTS

ELIGIBLE_QUALIFICATION = {"CHAMPION", "QUALIFIED_CHALLENGER"}

def validate_tournament_handoff(manifest: tuple[dict[str, Any], ...], artifacts: Mapping[str, Any]) -> None:
    if len(manifest) != 1:
        fail("P7_LTR_TOURNAMENT_HANDOFF_INVALID", "Tournament handoff must contain one manifest record")
    record = manifest[0]
    refs = artifact_map(record)
    if record.get("reference_count") != len(refs) or record.get("content_sha256") != digest(list(refs.values())):
        fail("P7_LTR_TOURNAMENT_HANDOFF_INVALID", "Tournament manifest reference closure mismatch")
    missing = sorted(set(REQUIRED_TOURNAMENT_ARTIFACTS) - set(refs))
    if missing:
        fail("P7_LTR_TOURNAMENT_HANDOFF_INVALID", f"missing Tournament references: {missing}")
    for name in REQUIRED_TOURNAMENT_ARTIFACTS:
        artifact = artifacts[name]
        ref = refs[name]
        expected = (artifact.artifact_id, artifact.content_sha256, artifact.record_count)
        actual = (ref.get("artifact_id"), ref.get("content_sha256"), ref.get("record_count"))
        if expected != actual:
            fail("P7_LTR_TOURNAMENT_HANDOFF_INVALID", f"Tournament reference mismatch for {name}")

def validate_tournament_candidate_sets(artifacts: Mapping[str, Any], decision_time: datetime) -> None:
    def keys(name: str) -> list[tuple[str, str]]:
        rows = artifacts[name].records
        values = [(str(row["comparison_group_id"]), str(row["candidate_id"])) for row in rows]
        if len(values) != len(set(values)):
            fail("P7_LTR_RUNTIME_DUPLICATE_CANDIDATE", f"duplicate candidate in {name}")
        return values
    expected = set(keys("factor_adjusted_candidate_panel"))
    for name in ("pareto_candidate_panel", "interpretable_score_panel",
                 "interpretable_score_decomposition_panel", "candidate_lineage_panel"):
        if set(keys(name)) != expected:
            fail("P7_LTR_RUNTIME_CANDIDATE_RECONCILIATION_FAILED", f"candidate set mismatch in {name}")
    groups = {str(row["comparison_group_id"]) for row in artifacts["comparison_group_registry"].records}
    if {group for group, _ in expected} - groups:
        fail("P7_LTR_RUNTIME_CANDIDATE_RECONCILIATION_FAILED", "candidate references unknown group")
    audit = artifacts["tournament_audit_report"].records
    if len(audit) != 1 or int(audit[0].get("candidate_count", -1)) != len(expected):
        fail("P7_LTR_RUNTIME_CANDIDATE_RECONCILIATION_FAILED", "Tournament audit count mismatch")
    for row in artifacts["factor_adjusted_candidate_panel"].records:
        available = parse_utc(row.get("feature_available_at"), field="feature_available_at")
        if available > decision_time:
            fail("P7_LTR_RUNTIME_FEATURE_FUTURE_DATED", "runtime feature was unavailable at decision time", candidate_id=str(row["candidate_id"]))

def _verify_model_hash(model: Mapping[str, Any]) -> None:
    payload = dict(model)
    supplied = payload.pop("model_hash", None)
    if not isinstance(supplied, str) or not supplied:
        fail("P7_LTR_RUNTIME_MODEL_HASH_MISSING", "model record is missing model_hash")
    if supplied != digest(payload):
        fail("P7_LTR_RUNTIME_MODEL_HASH_MISMATCH", "model declarative hash mismatch")
    if model.get("serialization_format") != "DECLARATIVE_JSON":
        fail("P7_LTR_RUNTIME_MODEL_SERIALIZATION_INVALID", "only declarative JSON models are accepted")

def _governance_by_hash(records: tuple[dict[str, Any], ...]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in records:
        model_hash = str(row.get("model_hash", ""))
        if not model_hash or model_hash in result:
            fail("P7_LTR_GOVERNANCE_REGISTRY_INVALID", "duplicate or missing governed model hash")
        result[model_hash] = dict(row)
    return result

def _qualification_by_hash(records: tuple[dict[str, Any], ...]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in records:
        model_hash = str(row.get("model_hash", ""))
        if not model_hash or model_hash in result:
            fail("P7_LTR_QUALIFICATION_REGISTRY_INVALID", "duplicate or missing qualified model hash")
        result[model_hash] = dict(row)
    return result

def _scope_covers(governed: Mapping[str, Any], candidates: tuple[dict[str, Any], ...]) -> bool:
    """GLOBAL_BATCH policy: one resolved model must cover the complete runtime batch."""
    objectives = set(governed.get("allowed_objective_families", []))
    horizons = set(governed.get("allowed_horizons", []))
    return all((not objectives or row["objective_family"] in objectives)
               and (not horizons or row["horizon"] in horizons) for row in candidates)

def _model_check_decision(
    model: Mapping[str, Any], qualification: Mapping[str, Any] | None,
    governance: Mapping[str, Any] | None, candidates: tuple[dict[str, Any], ...],
    policy: RuntimePolicy, decision_time: datetime, feature_schema_hash: str,
) -> tuple[dict[str, Any], bool]:
    checks: dict[str, bool] = {
        "qualification_record_present": qualification is not None,
        "governance_record_present": governance is not None,
    }
    if qualification is not None:
        checks.update({
            "qualification_eligible": qualification.get("qualification_status") in ELIGIBLE_QUALIFICATION,
            "runtime_eligible": bool(qualification.get("runtime_eligible")),
            "calibrator_ready": qualification.get("calibrator_status") == "CALIBRATED",
        })
    if governance is not None:
        approved_at = parse_utc(governance.get("approved_at"), field="approved_at")
        checks.update({
            "promoted": governance.get("promotion_status") == "PROMOTED",
            "not_deprecated": not bool(governance.get("deprecated", False)),
            "approved_before_decision": approved_at <= decision_time,
            "scope_covers_candidates": _scope_covers(governance, candidates),
        })
    cutoff = parse_utc(model["training_cutoff_at"], field="training_cutoff_at")
    checks.update({
        "implementation_allowed": model.get("implementation_id") in policy.allowed_implementation_ids,
        "feature_schema_match": model.get("feature_schema_hash") == feature_schema_hash,
        "target_match": model.get("target_id") == policy.required_target_id,
        "target_policy_match": model.get("target_policy_version") == policy.required_target_policy_version,
        "training_lag_satisfied": (decision_time - cutoff).total_seconds() > policy.min_training_lag_seconds,
    })
    failed = sorted(name for name, passed in checks.items() if not passed)
    eligible = not failed
    return {
        "model_family_id": model.get("model_family_id"),
        "model_hash": model.get("model_hash"),
        "checks": checks,
        "eligible": eligible,
        "failed_checks": failed,
        "reason_code": "P7_LTR_RUNTIME_MODEL_ELIGIBLE" if eligible else "P7_LTR_RUNTIME_MODEL_INELIGIBLE",
    }, eligible


def _eligible_models(
    model_records: tuple[dict[str, Any], ...], qualification: dict[str, dict[str, Any]],
    governance: dict[str, dict[str, Any]], candidates: tuple[dict[str, Any], ...],
    policy: RuntimePolicy, decision_time: datetime, feature_schema_hash: str,
) -> tuple[list[tuple[int, str, dict[str, Any], dict[str, Any], dict[str, Any]]], list[dict[str, Any]]]:
    eligible: list[tuple[int, str, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    decisions: list[dict[str, Any]] = []
    for raw in model_records:
        model = dict(raw)
        _verify_model_hash(model)
        qual = qualification.get(str(model["model_hash"]))
        governed = governance.get(str(model["model_hash"]))
        decision, is_eligible = _model_check_decision(
            model, qual, governed, candidates, policy, decision_time, feature_schema_hash
        )
        decisions.append(decision)
        if is_eligible:
            assert qual is not None and governed is not None
            eligible.append((int(governed.get("runtime_priority", 1000)), str(model["model_family_id"]),
                             model, dict(qual), dict(governed)))
    return eligible, decisions

def _selection_records(
    selected: tuple[int, str, dict[str, Any], dict[str, Any], dict[str, Any]] | None,
    *, requested: str, fallback: str, feature_schema_hash: str, candidate_count: int,
    decision_time: datetime, model_decisions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if requested == "INTERPRETABLE_ONLY":
        status, reason, selected = "INTERPRETABLE_ONLY", "P7_LTR_RUNTIME_DISABLED_BY_POLICY", None
    elif selected:
        status, reason = "RESOLVED", "P7_LTR_RUNTIME_MODEL_RESOLVED"
    else:
        status, reason = "UNAVAILABLE", "P7_LTR_RUNTIME_MODEL_UNAVAILABLE"
    model = selected[2] if selected else None
    report = [{
        "compatibility_status": status, "reason_code": reason, "requested_mode": requested,
        "fallback_mode": fallback, "feature_schema_hash": feature_schema_hash,
        "candidate_count": candidate_count, "decision_time": iso_utc(decision_time),
        "resolved_model_hash": model["model_hash"] if model else None,
        "resolved_model_family_id": model["model_family_id"] if model else None,
        "evaluated_model_count": len(model_decisions),
        "eligible_model_count": sum(1 for row in model_decisions if row["eligible"]),
        "model_decisions": model_decisions,
    }]
    if not selected:
        return report, []
    _, _, model, qual, governed = selected
    reference = {
        "model_family_id": model["model_family_id"], "implementation_id": model["implementation_id"],
        "model_hash": model["model_hash"], "feature_schema_hash": model["feature_schema_hash"],
        "target_id": model["target_id"], "target_policy_version": model["target_policy_version"],
        "training_cutoff_at": model["training_cutoff_at"], "calibrator_status": qual["calibrator_status"],
        "qualification_status": qual["qualification_status"], "governance_approval_id": governed["approval_id"],
        "runtime_priority": governed.get("runtime_priority", 1000), "model_record_digest": digest(model),
    }
    return report, [reference]

def resolve_runtime_model(
    model_records: tuple[dict[str, Any], ...], qualification_records: tuple[dict[str, Any], ...],
    governance_records: tuple[dict[str, Any], ...], candidates: tuple[dict[str, Any], ...],
    metric_records: tuple[dict[str, Any], ...], policy: RuntimePolicy, decision_time: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if policy.scope_mode != "GLOBAL_BATCH":
        fail("P7_LTR_RUNTIME_SCOPE_MODE_UNSUPPORTED", f"unsupported scope_mode {policy.scope_mode}")
    schema_hashes = {str(row["feature_schema_hash"]) for row in candidates}
    if len(schema_hashes) != 1:
        fail("P7_LTR_RUNTIME_FEATURE_SCHEMA_MISMATCH", "runtime candidates require one feature schema")
    feature_schema_hash = next(iter(schema_hashes))
    semantics = [row for row in metric_records if row.get("metric_id") == "interpretable_score"]
    if len(semantics) != 1 or semantics[0].get("scale_id") != policy.required_interpretable_scale_id:
        fail("P7_LTR_SCORE_SCALE_MISMATCH", "interpretable score scale is not compatible with blend policy")
    eligible, decisions = _eligible_models(model_records, _qualification_by_hash(qualification_records),
                                           _governance_by_hash(governance_records), candidates, policy,
                                           decision_time, feature_schema_hash)
    eligible.sort(key=lambda item: (item[0], item[1], item[2]["model_hash"]))
    selected = eligible[0] if eligible and policy.requested_mode != "INTERPRETABLE_ONLY" else None
    return _selection_records(selected, requested=policy.requested_mode, fallback=policy.fallback_mode,
                              feature_schema_hash=feature_schema_hash, candidate_count=len(candidates),
                              decision_time=decision_time, model_decisions=decisions)
