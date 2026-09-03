import pytest

from quant_pipeline.phase_00_zero_trust_guardian.modules._module_executor import ContractValidationError
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S4_M01_test_report_collector import run_module


FAMILIES = (
    "test_run_report_all_phases",
    "contract_test_report_all_phases",
    "schema_test_report_all_phases",
    "code_quality_test_report_all_phases",
)


def payload():
    return {
        family: [
            {
                "test_run_id": f"{family}-P{i}",
                "phase_id": f"P{i}",
                "total_tests": 1,
                "passed_tests": 1,
                "failed_tests": 0,
                "skipped_tests": 0,
                "status": "PASS",
            }
            for i in range(10)
        ]
        for family in FAMILIES
    }


def test_collects_exact_complete_phase_evidence():
    value = run_module(payload(), {"created_at": "2026-01-01T00:00:00Z"})["outputs"]["collected_test_reports"]
    assert value["status"] == "PASS"
    assert value["report_count"] == 40
    assert value["missing_expected_report_count"] == 0


def test_materializes_expected_evidence_gap_instead_of_crashing():
    value = payload()
    value[FAMILIES[0]].pop()
    result = run_module(value)["outputs"]["collected_test_reports"]
    assert result["status"] == "FAIL"
    assert result["missing_expected_report_count"] == 1
    assert result["release_blocking"]


def test_not_started_phase_does_not_create_false_failure():
    value = payload()
    for family in FAMILIES:
        value[family] = [report for report in value[family] if report["phase_id"] != "P9"]
    config = {"phase_lifecycle_statuses": {**{f"P{i}": "IMPLEMENTED" for i in range(9)}, "P9": "NOT_STARTED"}}
    result = run_module(value, config)["outputs"]["collected_test_reports"]
    p9 = next(item for item in result["phase_evidence"] if item["phase_id"] == "P9")
    assert result["status"] == "PASS"
    assert p9["evidence_status"] == "NOT_EXPECTED"


@pytest.mark.parametrize("mutation", ["duplicate_id", "bad_counts", "forbidden"])
def test_rejects_untrusted_reports(mutation):
    value = payload()
    if mutation == "duplicate_id":
        value[FAMILIES[0]][1]["test_run_id"] = value[FAMILIES[0]][0]["test_run_id"]
    elif mutation == "bad_counts":
        value[FAMILIES[0]][0]["passed_tests"] = 2
    else:
        value["target"] = "leak"
    with pytest.raises(ContractValidationError):
        run_module(value)
