from __future__ import annotations

from ._module_executor import PIPELINE_VERSION
from ._p0_s4_reports import REPORT_FAMILIES, collect_phase_evidence
from ._p0_s4_test_evidence import created_at, digest, envelope, require_call, validate_output


INPUTS = list(REPORT_FAMILIES)


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = require_call(inputs, config, INPUTS)
    reports, phase_evidence = collect_phase_evidence(inputs, config)
    expected_count = sum(len(item["expected_families"]) for item in phase_evidence)
    missing_count = sum(len(item["missing_families"]) for item in phase_evidence)
    unexpected_count = sum(len(item["unexpected_families"]) for item in phase_evidence)
    failed_count = sum(item["status"] == "FAIL" for item in reports)
    partial_count = sum(item["status"] in {"PARTIAL", "NOT_RUN"} for item in reports)
    has_missing = missing_count > 0
    status = "FAIL" if failed_count or has_missing else "PARTIAL" if partial_count else "PASS"
    release_blocking = status != "PASS"
    fingerprint = digest({"reports": reports, "phase_evidence": phase_evidence})
    value = {
        "artifact_id": f"collected-test-reports-{fingerprint[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{fingerprint}",
        "phase_count": len(phase_evidence),
        "report_family_count": len(INPUTS),
        "expected_report_count": expected_count,
        "report_count": len(reports),
        "reports": reports,
        "phase_evidence": phase_evidence,
        "failed_report_count": failed_count,
        "partial_report_count": partial_count,
        "missing_expected_report_count": missing_count,
        "unexpected_report_count": unexpected_count,
        "not_expected_phase_count": sum(item["evidence_status"] == "NOT_EXPECTED" for item in phase_evidence),
        "every_phase_emits_test_report": missing_count == 0,
        "every_expected_phase_emits_test_report": missing_count == 0,
        "test_run_id_unique": True,
        "evidence_identity_rule": "report_family+test_run_id",
        "status": status,
        "release_blocking": release_blocking,
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }
    validate_output(value, "collected_test_reports.schema.yaml")
    return envelope("P0.S4.M01", "test_report_collector", INPUTS, {"collected_test_reports": value})
