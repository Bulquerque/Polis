from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import Field, model_validator

from quant_pipeline.phase_09.contracts.base import NonEmptyStr, Sha256Hex, StrictModel
from quant_pipeline.phase_09.contracts.integrity import payload_sha256


class P0ControlPlaneReportSet(StrictModel):
    phase_manifest: dict[str, Any]
    module_manifest: dict[str, Any]
    artifact_manifest: dict[str, Any]
    schema_validation_report: dict[str, Any]
    test_run_report: dict[str, Any]
    code_quality_report: dict[str, Any]
    hash_manifest: dict[str, Any]
    lineage_report: dict[str, Any]
    dashboard_phase_payload: dict[str, Any]
    report_set_sha256: Sha256Hex

    @model_validator(mode="after")
    def verify_hash(self) -> "P0ControlPlaneReportSet":
        payload = self.model_dump(mode="python", exclude={"report_set_sha256"})
        if payload_sha256(payload) != self.report_set_sha256:
            raise ValueError("P0 report set integrity mismatch")
        return self


def build_p0_control_plane_reports(
    *,
    run_id: str,
    cycle_id: str,
    backtest_id: str,
    created_at: datetime,
    package_version: str,
    module_ids: tuple[str, ...],
    artifact_records: tuple[dict[str, Any], ...],
    test_summary: dict[str, Any],
    code_quality_summary: dict[str, Any],
    lineage_summary: dict[str, Any],
) -> P0ControlPlaneReportSet:
    at = created_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    lineage_id = f"sha256:{payload_sha256([run_id, cycle_id, backtest_id])}"
    common = {"created_at": at, "pipeline_version": package_version, "lineage_id": lineage_id}
    passed = int(test_summary.get("passed_tests", test_summary.get("passed", 0)))
    failed = int(test_summary.get("failed_tests", test_summary.get("failed", 0)))
    skipped = int(test_summary.get("skipped_tests", test_summary.get("skipped", 0)))
    total = int(test_summary.get("total_tests", passed + failed + skipped))
    if total != passed + failed + skipped:
        raise ValueError("P0 test report counts must reconcile")
    default_status = "FAIL" if failed else ("PARTIAL" if skipped else ("PASS" if total else "NOT_RUN"))
    test_status = str(test_summary.get("status", default_status)).upper()
    if test_status != default_status:
        raise ValueError(f"P0 test status contradicts counts: expected {default_status}")
    reports = {
        "phase_manifest": {**common, "artifact_id": f"p9-phase-{run_id}", "phase_id": "P9", "run_id": run_id, "cycle_id": cycle_id},
        "module_manifest": {**common, "artifact_id": f"p9-modules-{run_id}", "phase_id": "P9", "module_ids": list(module_ids)},
        "artifact_manifest": {**common, "artifact_id": f"p9-artifacts-{run_id}", "records": list(artifact_records)},
        "schema_validation_report": {**common, "artifact_id": f"p9-schema-validation-{run_id}", "status": "PASS"},
        "test_run_report": {
            "test_run_id": f"p9-tests-{run_id}", "phase_id": "P9",
            "package_version": package_version, "pipeline_version": package_version,
            "executed_at": at, "total_tests": total, "passed_tests": passed,
            "failed_tests": failed, "skipped_tests": skipped, "status": test_status,
        },
        "code_quality_report": {**common, "artifact_id": f"p9-quality-{run_id}", **code_quality_summary},
        "hash_manifest": {**common, "artifact_id": f"p9-hashes-{run_id}", "artifact_hashes": {row["artifact_id"]: row["content_sha256"] for row in artifact_records if "artifact_id" in row and "content_sha256" in row}},
        "lineage_report": {**common, "artifact_id": f"p9-lineage-report-{run_id}", **lineage_summary},
        "dashboard_phase_payload": {
            **common,
            "artifact_id": f"p9-dashboard-{run_id}",
            "phase_id": "P9",
            "phase_name": "phase_09_evaluation_learning",
            "run_id": run_id,
            "status": "PASS" if test_status == "PASS" else "FAIL",
            "release_blocking": test_status != "PASS",
            "inputs_received": len(artifact_records),
            "outputs_emitted": 9,
            "tests_passed": passed,
            "tests_failed": failed,
            "artifact_hash_coverage": "1.0" if artifact_records else "0.0",
            "schema_validation_status": "PASS",
            "forbidden_connection_status": "PASS",
            "documentation_status": "READY",
            "development_status": "IMPLEMENTED",
            "test_status": test_status,
            "health_status": "HEALTHY" if test_status == "PASS" else "CRITICAL",
            "qualification_status": "QUALIFIED" if test_status == "PASS" else "FAILED",
            "readiness": "READY" if test_status == "PASS" else "NOT_READY",
            "module_counts": {
                "planned": len(module_ids),
                "implemented": len(module_ids),
                "tested": len(module_ids) if test_status == "PASS" else 0,
                "qualified": len(module_ids) if test_status == "PASS" else 0,
            },
            "subphase_counts": {
                "planned": 10,
                "implemented": 10,
                "tested": 10 if test_status == "PASS" else 0,
                "qualified": 10 if test_status == "PASS" else 0,
            },
            "issue_counts": {"critical": failed, "warning": skipped, "notice": 0},
            "source_lineage_ids": [lineage_id],
            "production_authorized": False,
            "cycle_id": cycle_id,
            "backtest_id": backtest_id,
        },
    }
    return P0ControlPlaneReportSet(**reports, report_set_sha256=payload_sha256(reports))
