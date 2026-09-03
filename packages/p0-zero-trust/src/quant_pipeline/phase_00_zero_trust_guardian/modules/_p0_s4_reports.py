from __future__ import annotations

from typing import Any

from ._module_executor import ContractValidationError
from ._p0_s4_test_evidence import PHASES, PHASE_SET


REPORT_FAMILIES = (
    "test_run_report_all_phases",
    "contract_test_report_all_phases",
    "schema_test_report_all_phases",
    "code_quality_test_report_all_phases",
)
NOT_STARTED_STATES = {"NOT_STARTED", "PLANNED", "NOT_AUTHORIZED"}


def lifecycle_map(config: dict[str, Any]) -> dict[str, str]:
    raw = config.get("phase_lifecycle_statuses")
    if raw is None:
        return {phase: "IMPLEMENTED" for phase in PHASES}
    if not isinstance(raw, dict):
        raise ContractValidationError("phase_lifecycle_statuses must be a mapping")
    result = {}
    for phase in PHASES:
        value = raw.get(phase, "NOT_STARTED")
        if isinstance(value, dict):
            value = value.get("status") or value.get("implementation_status")
        if not isinstance(value, str) or not value:
            raise ContractValidationError(f"invalid lifecycle status for {phase}")
        result[phase] = value.upper()
    unknown = sorted(set(raw).difference(PHASE_SET))
    if unknown:
        raise ContractValidationError(f"unknown phases in lifecycle map: {unknown}")
    return result


def _container_reports(value: Any, family: str) -> list[dict[str, Any]]:
    if isinstance(value, dict) and isinstance(value.get("reports"), list):
        value = value["reports"]
    elif isinstance(value, dict) and set(value).issubset(PHASE_SET):
        value = [dict(report, phase_id=phase) if isinstance(report, dict) and "phase_id" not in report else report for phase, report in value.items()]
    if not isinstance(value, list):
        raise ContractValidationError(f"{family} must contain a reports list")
    return value


def _derived_status(report: dict[str, Any], skipped_policy: str) -> str:
    total = report["total_tests"]
    failed = report["failed_tests"]
    skipped = report["skipped_tests"]
    if failed:
        return "FAIL"
    if total == 0:
        return "NOT_RUN"
    if skipped:
        return "FAIL" if skipped_policy == "fail" else "PARTIAL"
    return "PASS"


def normalize_family(value: Any, family: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    skipped_policy = str(config.get("skipped_test_policy", "partial")).lower()
    if skipped_policy not in {"partial", "fail"}:
        raise ContractValidationError("skipped_test_policy must be partial or fail")
    normalized = []
    seen_ids: set[str] = set()
    for index, report in enumerate(_container_reports(value, family)):
        if not isinstance(report, dict):
            raise ContractValidationError(f"{family}[{index}] must be a mapping")
        required = {"test_run_id", "phase_id", "total_tests", "passed_tests", "failed_tests", "skipped_tests", "status"}
        missing = sorted(required.difference(report))
        if missing:
            raise ContractValidationError(f"{family}[{index}] missing fields: {missing}")
        phase = report["phase_id"]
        run_id = report["test_run_id"]
        counts = [report[key] for key in ("total_tests", "passed_tests", "failed_tests", "skipped_tests")]
        if phase not in PHASE_SET or not isinstance(run_id, str) or not run_id:
            raise ContractValidationError(f"{family}[{index}] has invalid identity")
        if run_id in seen_ids:
            raise ContractValidationError(f"{family} contains duplicate test_run_id: {run_id}")
        seen_ids.add(run_id)
        if not all(isinstance(count, int) and not isinstance(count, bool) and count >= 0 for count in counts):
            raise ContractValidationError(f"{family}[{index}] has invalid counts")
        if counts[0] != sum(counts[1:]):
            raise ContractValidationError(f"{family}[{index}] counts do not reconcile")
        derived = _derived_status(report, skipped_policy)
        declared = str(report["status"]).upper()
        legacy_allowed = derived == "PARTIAL" and declared == "FAIL"
        if declared != derived and not legacy_allowed:
            raise ContractValidationError(f"{family}[{index}] status contradicts counts: expected {derived}")
        normalized.append({"report_family": family, **report, "status": derived})
    return normalized


def collect_phase_evidence(inputs: dict[str, Any], config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lifecycle = lifecycle_map(config)
    by_family = {family: normalize_family(inputs[family], family, config) for family in REPORT_FAMILIES}
    reports = [item for family in REPORT_FAMILIES for item in by_family[family]]
    phase_evidence = []
    for phase in PHASES:
        lifecycle_status = lifecycle[phase]
        expected = [] if lifecycle_status in NOT_STARTED_STATES else list(REPORT_FAMILIES)
        received = sorted(item["report_family"] for item in reports if item["phase_id"] == phase)
        missing = sorted(set(expected).difference(received))
        unexpected = sorted(set(received).difference(expected))
        phase_reports = [item for item in reports if item["phase_id"] == phase]
        statuses = {item["status"] for item in phase_reports}
        if missing:
            evidence_status = "MISSING"
        elif not expected and not received:
            evidence_status = "NOT_EXPECTED"
        elif "FAIL" in statuses:
            evidence_status = "FAIL"
        elif "PARTIAL" in statuses or "NOT_RUN" in statuses:
            evidence_status = "PARTIAL"
        else:
            evidence_status = "COMPLETE"
        phase_evidence.append({
            "phase_id": phase,
            "lifecycle_status": lifecycle_status,
            "expected_families": expected,
            "received_families": received,
            "missing_families": missing,
            "unexpected_families": unexpected,
            "evidence_status": evidence_status,
        })
    return reports, phase_evidence
