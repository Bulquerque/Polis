from __future__ import annotations

from collections import defaultdict
from typing import Any

from ._module_executor import ContractValidationError
from ._p0_s4_test_evidence import PHASES


def _legacy_phase_evidence(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = defaultdict(list)
    for report in reports:
        phase = report.get("phase_id")
        if phase not in PHASES:
            raise ContractValidationError("collected reports contain malformed phase evidence")
        grouped[phase].append(report)
    evidence = []
    for phase in PHASES:
        phase_reports = grouped[phase]
        if len(phase_reports) != 4:
            raise ContractValidationError(f"{phase} must have four collected report families")
        failed = sum(int(item.get("failed_tests", 0)) for item in phase_reports)
        skipped = sum(int(item.get("skipped_tests", 0)) for item in phase_reports)
        status = "FAIL" if failed else "PARTIAL" if skipped else "PASS"
        evidence.append({
            "phase_id": phase,
            "lifecycle_status": "IMPLEMENTED",
            "expected_families": [f"legacy-{i}" for i in range(4)],
            "received_families": [f"legacy-{i}" for i in range(4)],
            "missing_families": [],
            "unexpected_families": [],
            "evidence_status": status,
        })
    return evidence


def phase_test_states(collected: dict[str, Any]) -> list[dict[str, Any]]:
    raw = collected.get("phase_evidence")
    if not isinstance(raw, list):
        reports = collected.get("reports")
        if not isinstance(reports, list) or not reports:
            raise ContractValidationError("collected_test_reports has no material reports")
        raw = _legacy_phase_evidence(reports)
    by_phase = {}
    for item in raw:
        if not isinstance(item, dict) or item.get("phase_id") not in PHASES:
            raise ContractValidationError("phase evidence is malformed")
        by_phase[item["phase_id"]] = item
    if set(by_phase) != set(PHASES):
        raise ContractValidationError("phase evidence must cover P0-P9 exactly once")
    states = []
    for phase in PHASES:
        item = by_phase[phase]
        evidence_status = item.get("evidence_status")
        lifecycle = str(item.get("lifecycle_status", "IMPLEMENTED"))
        if evidence_status == "NOT_EXPECTED":
            status, blocking, reasons = "NOT_RUN", False, ["PHASE_NOT_STARTED"]
        elif evidence_status == "MISSING":
            status, blocking, reasons = "FAIL", True, ["EXPECTED_TEST_EVIDENCE_MISSING"]
        elif evidence_status == "FAIL":
            status, blocking, reasons = "FAIL", True, ["PHASE_REPORTED_TEST_FAILURE"]
        elif evidence_status == "PARTIAL":
            status, blocking, reasons = "PARTIAL", True, ["PARTIAL_TEST_EXECUTION"]
        else:
            status, blocking, reasons = "PASS", False, []
        states.append({
            "phase_id": phase,
            "lifecycle_status": lifecycle,
            "test_status": status,
            "status": status,
            "release_blocking": blocking,
            "reason_codes": reasons,
            "expected_report_count": len(item.get("expected_families", [])),
            "received_report_count": len(item.get("received_families", [])),
            "missing_report_count": len(item.get("missing_families", [])),
        })
    return states


def independent_control(name: str, item: dict[str, Any]) -> dict[str, Any]:
    status = item.get("status")
    blocking = item.get("release_blocking") is True
    passed = status == "PASS" and not blocking
    return {
        "control": name,
        "artifact_id": item.get("artifact_id", name),
        "lineage_id": item.get("lineage_id"),
        "status": "PASS" if passed else "FAIL",
        "release_blocking": not passed,
    }



def build_test_outputs(
    phases: list[dict[str, Any]],
    controls: list[dict[str, Any]],
    common: dict[str, Any],
    fingerprint: str,
    source_lineage_ids: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    failing = sum(item["test_status"] == "FAIL" for item in phases)
    partial = sum(item["test_status"] == "PARTIAL" for item in phases)
    not_run = sum(item["test_status"] == "NOT_RUN" for item in phases)
    passing = sum(item["test_status"] == "PASS" for item in phases)
    control_failures = sum(item["status"] == "FAIL" for item in controls)
    blocking = bool(control_failures or failing or partial)
    status = "FAIL" if blocking else "PASS"
    global_report = {
        "artifact_id": f"global-test-report-{fingerprint[:12]}",
        **common,
        "source_lineage_ids": source_lineage_ids,
        "phase_reported_test_health": phases,
        "independent_controls": controls,
        "critical_tests": len(controls),
        "critical_failed_tests": control_failures + failing + partial,
        "phase_count": len(phases),
        "phases": phases,
        "phase_pass_count": passing,
        "phase_fail_count": failing,
        "phase_partial_count": partial,
        "phase_not_run_count": not_run,
        "critical_tests_classified": True,
        "phase_status_computed": True,
        "status": status,
        "release_blocking": blocking,
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }
    panel = {
        "artifact_id": f"phase-test-status-panel-{fingerprint[:12]}",
        **common,
        "phase_count": len(phases),
        "phases": phases,
        "passing_phase_count": passing,
        "failing_phase_count": failing,
        "partial_phase_count": partial,
        "not_run_phase_count": not_run,
        "blocked_phase_count": failing + partial,
        "phase_status_computed": True,
        "status": status,
        "release_blocking": blocking,
    }
    return global_report, panel
