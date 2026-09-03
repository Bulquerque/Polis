from __future__ import annotations

from typing import Any

READY_PHASE_STATES = {"PASS", "APPROVED", "READY", "QUALIFIED", "PHASE_QUALIFIED"}
FAILED_PHASE_STATES = {"FAIL", "QUALIFICATION_FAILED"}


def evaluate_material(label: str, data: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    evaluator = _MATERIAL_EVALUATORS.get(label, _evaluate_generic)
    blocked, reasons = evaluator(data)
    if blocked and not reasons:
        reasons.append(_reason("UPSTREAM_GATE_FAILURE", label, "material upstream report is blocking"))
    return blocked, reasons


def _evaluate_release_manifest(data: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    blocked = _base_blocked(data) or not _manifest_traceable(data)
    reasons = []
    if data.get("snapshot_coherence_status") == "MISMATCH":
        reasons.append(_reason("SNAPSHOT_MISMATCH", "release_manifest", "release material references different snapshots"))
    return blocked, reasons


def _evaluate_global_tests(data: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    failed = _nonzero(data, "critical_failed_tests")
    reasons = [_reason("CRITICAL_TEST_FAILURE", "global_test_report", "critical tests failed")] if failed else []
    return _base_blocked(data) or failed, reasons


def _evaluate_connections(data: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    count = _first_int(data, "forbidden_connection_count", "violation_count", "finding_count")
    failed = count != 0
    reasons = [_reason("FORBIDDEN_CONNECTION", "forbidden_connection_report", "forbidden connections detected")] if failed else []
    return _base_blocked(data) or failed, reasons


def _evaluate_hashes(data: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    failed = data.get("hash_mismatch_count") != 0
    reasons = [_reason("HASH_MISMATCH", "hash_integrity_report", "hash mismatches detected")] if failed else []
    return _base_blocked(data) or failed, reasons


def _evaluate_agent_package(data: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    invalid = data.get("package_structure_valid") is not True or data.get("no_cache_in_zip") is not True
    reasons = [_reason("INVALID_AGENT_PACKAGE", "agent_package_validation_report", "agent package validation failed")] if invalid else []
    return _base_blocked(data) or invalid, reasons


def _evaluate_code_quality(data: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    blocked = _base_blocked(data)
    reasons = [_reason("CODE_QUALITY_BLOCKER", "code_quality_report", "code quality report is blocking")] if blocked else []
    return blocked, reasons


def _evaluate_generic(data: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    return _base_blocked(data), []


_MATERIAL_EVALUATORS = {
    "release_manifest": _evaluate_release_manifest,
    "global_test_report": _evaluate_global_tests,
    "forbidden_connection_report": _evaluate_connections,
    "code_quality_report": _evaluate_code_quality,
    "hash_integrity_report": _evaluate_hashes,
    "agent_package_validation_report": _evaluate_agent_package,
}

def phase_readiness(phases: list[dict[str, Any]], release_scope: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolved: list[dict[str, Any]] = []
    reasons: list[dict[str, Any]] = []
    for item in phases:
        phase_id = item.get("phase_id")
        status = str(item.get("status") or "UNKNOWN").upper()
        if not isinstance(phase_id, str):
            continue
        if status in READY_PHASE_STATES:
            readiness = "READY"
        elif status in FAILED_PHASE_STATES:
            readiness = "BLOCKED"
            reasons.append(_reason("PHASE_VALIDATION_FAILURE", "global_test_report", f"{phase_id} failed validation", phase_id))
        else:
            readiness = "NOT_READY"
            if _scope_requires_phase(release_scope, phase_id):
                reasons.append(_reason("PHASE_NOT_READY", "global_test_report", f"{phase_id} is not ready", phase_id, "INCOMPLETE"))
        resolved.append(
            {
                "phase_id": phase_id,
                "source_status": status,
                "readiness": readiness,
                "findings": item.get("findings", []) if isinstance(item.get("findings"), list) else [],
            }
        )
    return resolved, reasons


def blocking_kind(reasons: list[dict[str, Any]]) -> list[str]:
    return sorted({str(reason.get("blocking_kind", "VALIDATION_FAILURE")) for reason in reasons})


def _scope_requires_phase(release_scope: str, phase_id: str) -> bool:
    scope = release_scope.upper()
    if scope in {"P0_ONLY", "P0_COMPONENT_RELEASE", "P0_TECHNICAL_CLOSURE"}:
        return phase_id == "P0"
    return True


def _base_blocked(data: dict[str, Any]) -> bool:
    return data.get("status") in {"FAIL", "BLOCKED"} or data.get("release_blocking") is True or data.get("blocking") is True


def _manifest_traceable(data: dict[str, Any]) -> bool:
    artifacts = data.get("artifacts")
    return (
        isinstance(artifacts, list)
        and len(artifacts) >= 3
        and data.get("release_artifacts_listed") is True
        and data.get("release_manifest_traceable") is True
    )


def _nonzero(data: dict[str, Any], key: str) -> bool:
    value = data.get(key)
    return isinstance(value, int) and value != 0


def _first_int(data: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = data.get(key)
        if isinstance(value, int):
            return value
    return -1


def _reason(
    code: str,
    artifact: str,
    detail: str,
    owner_phase: str | None = None,
    kind: str = "VALIDATION_FAILURE",
) -> dict[str, Any]:
    return {
        "code": code,
        "artifact": artifact,
        "detail": detail,
        "owner_phase": owner_phase,
        "blocking_kind": kind,
        "release_blocking": True,
    }
