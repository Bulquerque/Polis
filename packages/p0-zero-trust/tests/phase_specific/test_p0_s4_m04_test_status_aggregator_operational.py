import pytest

from quant_pipeline.phase_00_zero_trust_guardian.modules._module_executor import ContractValidationError
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S4_M04_test_status_aggregator import run_module


LINEAGE = "sha256:" + "a" * 64


def payload(fail=False):
    reports = [{"phase_id": f"P{i}", "failed_tests": int(fail and i == 0), "skipped_tests": 0} for i in range(10) for _ in range(4)]
    return {
        "collected_test_reports": {"reports": reports, "status": "FAIL" if fail else "PASS", "release_blocking": fail, "lineage_id": LINEAGE},
        "contract_test_report": {"status": "PASS", "release_blocking": False, "lineage_id": LINEAGE},
        "schema_test_report": {"status": "PASS", "release_blocking": False, "lineage_id": LINEAGE},
    }


def test_aggregates_complete_panel():
    result = run_module(payload(), {"created_at": "2026-01-01T00:00:00Z"})["outputs"]
    assert result["global_test_report"]["status"] == "PASS"
    assert result["phase_test_status_panel"]["passing_phase_count"] == 10


def test_exposes_failure_as_test_health_not_blocked_status():
    result = run_module(payload(True))["outputs"]["global_test_report"]
    assert result["status"] == "FAIL"
    assert result["release_blocking"]
    assert result["critical_failed_tests"] > 0


def test_not_started_phase_is_not_run_without_false_failure():
    phase_evidence = [
        {
            "phase_id": f"P{i}",
            "lifecycle_status": "NOT_STARTED" if i == 9 else "IMPLEMENTED",
            "expected_families": [] if i == 9 else ["a", "b", "c", "d"],
            "received_families": [] if i == 9 else ["a", "b", "c", "d"],
            "missing_families": [],
            "unexpected_families": [],
            "evidence_status": "NOT_EXPECTED" if i == 9 else "COMPLETE",
        }
        for i in range(10)
    ]
    value = payload()
    value["collected_test_reports"] = {"phase_evidence": phase_evidence, "lineage_id": LINEAGE, "status": "PASS", "release_blocking": False}
    panel = run_module(value)["outputs"]["phase_test_status_panel"]
    p9 = next(item for item in panel["phases"] if item["phase_id"] == "P9")
    assert p9["test_status"] == "NOT_RUN"
    assert not p9["release_blocking"]
    assert panel["status"] == "PASS"


def test_rejects_missing_phase_family():
    value = payload()
    value["collected_test_reports"]["reports"].pop()
    with pytest.raises(ContractValidationError):
        run_module(value)
