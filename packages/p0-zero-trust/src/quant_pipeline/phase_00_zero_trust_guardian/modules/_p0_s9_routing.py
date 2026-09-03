from __future__ import annotations

from typing import Any

from ._module_executor import ContractValidationError
from ._p0_s9_feedback import BLOCK, NO_BLOCK, NO_RELEASE_BLOCK, RELEASE_BLOCK
from ._p0_s9_models import normalize_finding


def phase_items(source: dict[str, Any], source_name: str) -> list[dict[str, Any]]:
    for key in ("phases", "phase_statuses"):
        values = source.get(key)
        if isinstance(values, list):
            if not all(isinstance(item, dict) and isinstance(item.get("phase_id"), str) for item in values):
                raise ContractValidationError(f"{source_name}.{key} contains malformed phase entries")
            return values
    raise ContractValidationError(f"{source_name} must contain phases or phase_statuses")


def expected_phase_ids(sources: dict[str, dict[str, Any]]) -> list[str]:
    authority_name = "phase_health_panel" if "phase_health_panel" in sources else next(iter(sources))
    authority = phase_items(sources[authority_name], authority_name)
    values = sorted({item["phase_id"] for item in authority}, key=_phase_sort_key)
    if not values:
        raise ContractValidationError("feedback routing has no registered phases")
    for source_name, source in sources.items():
        actual = {item["phase_id"] for item in phase_items(source, source_name)}
        if actual != set(values):
            raise ContractValidationError(f"{source_name} phase coverage differs from canonical feedback phase set")
    return values


def collect_findings(sources: dict[str, dict[str, Any]], phase_ids: list[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for source_name, source in sources.items():
        for phase in phase_items(source, source_name):
            phase_id = phase["phase_id"]
            values = phase.get("findings", [])
            if values is None:
                values = []
            if not isinstance(values, list):
                raise ContractValidationError(f"{source_name}.{phase_id}.findings must be a list")
            normalized = [normalize_finding(item, phase_id, source_name) for item in values]
            findings.extend(normalized)
            if source_name == "phase_health_panel":
                findings.extend(synthesize_health_findings(phase, source_name))
            findings.extend(_unexplained_failure(phase, normalized, source_name))
    unknown = {item["owner_phase"] for item in findings if item["owner_phase"] not in phase_ids}
    if unknown:
        raise ContractValidationError(f"feedback findings reference unknown owner phases: {sorted(unknown)}")
    return findings


def synthesize_health_findings(phase: dict[str, Any], source: str) -> list[dict[str, Any]]:
    phase_id = phase["phase_id"]
    raw: list[dict[str, Any]] = []
    development = phase.get("development_status")
    if development == "NOT_STARTED":
        raw.append(_finding(phase_id, "DEVELOPMENT_NOT_STARTED", "NOTICE", "NOT_STARTED", "phase has not started", False, False))
    elif development == "IN_DEVELOPMENT":
        raw.append(_finding(phase_id, "DEVELOPMENT_INCOMPLETE", "NOTICE", "INCOMPLETE", "phase is still in development", False, False))
    if phase.get("test_status") == "FAIL":
        raw.append(_finding(phase_id, "TEST_FAILURE", "ERROR", "TEST_FAILURE", "phase tests are failing", True))
    if phase.get("health_status") == "CRITICAL":
        raw.append(_finding(phase_id, "HEALTH_CRITICAL", "CRITICAL", "FAILURE", "phase health is critical", True))
    qualification = phase.get("qualification_status")
    if qualification == "FAILED":
        raw.append(_finding(phase_id, "QUALIFICATION_FAILED", "ERROR", "QUALIFICATION_FAILURE", "phase qualification failed", True))
    elif development == "IMPLEMENTED" and qualification not in {None, "QUALIFIED"}:
        raw.append(_finding(phase_id, "QUALIFICATION_INCOMPLETE", "NOTICE", "QUALIFICATION_INCOMPLETE", "phase is not yet qualified", False, False))
    return [normalize_finding(item, phase_id, source) for item in raw]


def group_by_phase(findings: list[dict[str, Any]], phase_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    result = {phase_id: [] for phase_id in phase_ids}
    for item in findings:
        result[item["owner_phase"]].append(item)
    return result


def _unexplained_failure(phase: dict[str, Any], normalized: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    if phase.get("status") not in {"FAIL", "BLOCKED"}:
        return []
    if any(item["readiness_blocking"] or item["release_blocking"] for item in normalized):
        return []
    phase_id = phase["phase_id"]
    raw = _finding(
        phase_id,
        f"UNEXPLAINED_{source.upper()}_FAILURE",
        "ERROR",
        "MISSING_EVIDENCE",
        f"{source} reports failure without an explicit blocking finding",
        True,
    )
    return [normalize_finding(raw, phase_id, source)]


def _finding(
    phase_id: str,
    reason: str,
    severity: str,
    condition: str,
    message: str,
    action_required: bool,
    blocks_release: bool = True,
) -> dict[str, Any]:
    return {
        "finding_id": f"{phase_id}:{reason}",
        "reason_code": reason,
        "severity": severity,
        "condition_type": condition,
        "readiness_impact": BLOCK,
        "release_impact": RELEASE_BLOCK if blocks_release else NO_RELEASE_BLOCK,
        "message": message,
        "owner": phase_id,
        "action_required": action_required,
        "action": "review and resolve the reported condition" if action_required else "",
    }


def _phase_sort_key(value: str) -> tuple[int, str]:
    try:
        return int(value[1:]), value
    except (TypeError, ValueError):
        return 10**9, value
