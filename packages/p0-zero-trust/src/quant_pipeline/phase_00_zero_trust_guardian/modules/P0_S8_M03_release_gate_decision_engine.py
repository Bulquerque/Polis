from __future__ import annotations

from typing import Any

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s8_utils import (
    artifact,
    created_at,
    digest,
    envelope,
    promotion_allowed,
    reject_forbidden,
    source_record,
)
from ._s8_gate_rules import blocking_kind, evaluate_material, phase_readiness

_REQUIRED = [
    "release_manifest",
    "global_test_report",
    "forbidden_connection_report",
    "code_quality_report",
    "hash_integrity_report",
    "agent_package_validation_report",
]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    _validate_inputs(inputs)
    reject_forbidden(inputs)
    evaluations, reasons = _evaluate_inputs(inputs)
    manifest = inputs["release_manifest"]
    release_scope = str(manifest.get("release_scope") or "FULL_PIPELINE")
    phases = _phase_inputs(inputs["global_test_report"])
    phase_states, phase_reasons = phase_readiness(phases, release_scope)
    reasons.extend(phase_reasons)
    report = _build_report(config, manifest, evaluations, reasons, phase_states, release_scope)
    return envelope(
        "P0.S8.M03",
        "release_gate_decision_engine",
        "P0_S8_M03_release_gate_decision_engine.yaml",
        _REQUIRED,
        "release_gate_report",
        report,
    )


def _validate_inputs(inputs: Any) -> None:
    if not isinstance(inputs, dict) or any(key not in inputs for key in _REQUIRED):
        raise ContractValidationError("missing required P0.S8.M03 inputs")


def _evaluate_inputs(inputs: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evaluations: list[dict[str, Any]] = []
    reasons: list[dict[str, Any]] = []
    for label in _REQUIRED:
        data, source, source_hash = artifact(inputs[label], label)
        _validate_typed_material(label, data)
        blocked, material_reasons = evaluate_material(label, data)
        evaluation = source_record(label, data, source, source_hash)
        evaluation.update({"status": data.get("status", "PASS"), "blocking": blocked})
        evaluations.append(evaluation)
        reasons.extend(material_reasons)
    return evaluations, _deduplicate_reasons(reasons)


def _validate_typed_material(label: str, data: dict[str, Any]) -> None:
    validator = _TYPED_VALIDATORS.get(label)
    if validator is not None:
        validator(data)


def _validate_release_manifest(data: dict[str, Any]) -> None:
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) < 3:
        raise ContractValidationError("release_manifest lacks material traceability")
    if data.get("release_artifacts_listed") is not True or data.get("release_manifest_traceable") is not True:
        raise ContractValidationError("release_manifest lacks material traceability")


def _validate_global_test_report(data: dict[str, Any]) -> None:
    if not isinstance(data.get("critical_failed_tests"), int):
        raise ContractValidationError("global_test_report.critical_failed_tests must be integer")


def _validate_forbidden_connections(data: dict[str, Any]) -> None:
    count = data.get("forbidden_connection_count", data.get("violation_count", data.get("finding_count")))
    if not isinstance(count, int):
        raise ContractValidationError("forbidden_connection_report lacks typed violation count")


def _validate_hash_integrity(data: dict[str, Any]) -> None:
    if not isinstance(data.get("hash_mismatch_count"), int):
        raise ContractValidationError("hash_integrity_report.hash_mismatch_count must be integer")


_TYPED_VALIDATORS = {
    "release_manifest": _validate_release_manifest,
    "global_test_report": _validate_global_test_report,
    "forbidden_connection_report": _validate_forbidden_connections,
    "hash_integrity_report": _validate_hash_integrity,
}

def _phase_inputs(global_test_report: dict[str, Any]) -> list[dict[str, Any]]:
    phases = global_test_report.get("phases")
    if not isinstance(phases, list) or not phases:
        raise ContractValidationError("global_test_report must provide phase results")
    for item in phases:
        if not isinstance(item, dict) or not isinstance(item.get("phase_id"), str):
            raise ContractValidationError("global_test_report contains malformed phase result")
    if not any(item.get("phase_id") == "P0" for item in phases):
        raise ContractValidationError("global_test_report must provide P0 phase result")
    return phases


def _build_report(
    config: dict[str, Any],
    manifest: dict[str, Any],
    evaluations: list[dict[str, Any]],
    reasons: list[dict[str, Any]],
    phases: list[dict[str, Any]],
    release_scope: str,
) -> dict[str, Any]:
    blocking = bool(reasons)
    warnings = _collect_warnings(manifest)
    body = {
        "release_id": manifest.get("release_id", PIPELINE_VERSION),
        "release_fingerprint": manifest.get("release_fingerprint", ""),
        "release_scope": release_scope,
        "evaluations": evaluations,
        "blocking_reasons": reasons,
        "reason_codes": sorted({reason["code"] for reason in reasons}),
        "blocking_kinds": blocking_kind(reasons),
        "warnings": warnings,
        "phases": phases,
        "phase_readiness": phases,
    }
    checksum = digest(body)
    return {
        "artifact_id": f"release-gate-report-{checksum[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{checksum}",
        **body,
        "evaluated_artifact_count": len(evaluations),
        "decision": "FAIL" if blocking else "PASS",
        "readiness_state": "NOT_READY" if blocking else "READY",
        "critical_test_failure_evaluated": True,
        "forbidden_connection_evaluated": True,
        "agent_package_evaluated": True,
        "qualification_evaluated": manifest.get("qualification_status") == "BOUND",
        "snapshot_coherence_evaluated": manifest.get("snapshot_coherence_status") in {"BOUND", "MATERIAL_ONLY", "MISMATCH"},
        "status": "FAIL" if blocking else "PASS",
        "release_blocking": blocking,
        "validation_evidence_status": _validation_evidence_status(manifest, blocking),
        "validation_evidence_state": _rich_validation_state(manifest, blocking),
        "deployment_authorization": {
            "status": "NOT_REQUESTED",
            "release_blocking": False,
        },
        "production_promotion_allowed": False,
        # Technical approval and the production authorization policy are
        # separate.  The qualification runner omits the production flag and
        # therefore remains fail-closed; an explicit false production policy
        # is reported without turning the technical gate into a blocker.
        "promotion_blocked": config.get("production_promotion_allowed") is not False,
    }


def _collect_warnings(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    warnings = []
    if manifest.get("qualification_status") != "BOUND":
        warnings.append({"code": "QUALIFICATION_NOT_BOUND", "detail": "release manifest has no canonical qualification binding"})
    if manifest.get("snapshot_coherence_status") == "MATERIAL_ONLY":
        warnings.append({"code": "SOURCE_SNAPSHOT_NOT_EXPLICIT", "detail": "release identity is bound to material hashes, not an explicit source snapshot"})
    return warnings


def _validation_evidence_status(manifest: dict[str, Any], blocking: bool) -> str:
    if blocking:
        return "domain_oracle_pass_pending_independent_judge"
    return "domain_oracle_pass_pending_independent_judge"


def _rich_validation_state(manifest: dict[str, Any], blocking: bool) -> str:
    if blocking:
        return "VALIDATION_BLOCKED"
    if manifest.get("qualification_status") == "BOUND":
        return "QUALIFICATION_BOUND"
    return "INDEPENDENT_VERIFICATION_PENDING"


def _deduplicate_reasons(reasons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    output = []
    for reason in reasons:
        key = (reason.get("code"), reason.get("artifact"), reason.get("owner_phase"), reason.get("detail"))
        if key not in seen:
            seen.add(key)
            output.append(reason)
    return output
