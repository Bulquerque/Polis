import pytest

from quant_pipeline.phase_00_zero_trust_guardian.modules._module_executor import ContractValidationError
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S4_M03_schema_test_orchestrator import run_module


SCHEMA_PATH = "phase_00_zero_trust/phase_00_zero_trust_guardian_agent_package_RC4_1/schemas/test_run_report.schema.yaml"


def valid_payload():
    return {"test_run_id": "run", "phase_id": "P0", "package_version": "1", "pipeline_version": "V14.1-RC4.1", "executed_at": "now", "total_tests": 1, "passed_tests": 1, "failed_tests": 0, "skipped_tests": 0, "status": "PASS"}


def payload():
    return {"schema_registry": {"schemas": [{"schema_id": "test_run_report.v1", "path": SCHEMA_PATH}]}, "fixtures_all_phases": {"fixtures": [{"fixture_id": "valid", "schema_id": "test_run_report.v1", "expectation": "valid", "payload": valid_payload()}, {"fixture_id": "invalid", "schema_id": "test_run_report.v1", "expectation": "invalid", "payload": {}}]}}


def test_executes_positive_and_negative_fixtures():
    report = run_module(payload(), {"created_at": "2026-01-01T00:00:00Z"})["outputs"]["schema_test_report"]
    assert report["status"] == "PASS" and report["fixture_count"] == 2


@pytest.mark.parametrize("mutation", ["coverage", "unknown", "duplicate", "bad_expectation"])
def test_rejects_fixture_evidence_gaps(mutation):
    value = payload(); fixtures = value["fixtures_all_phases"]["fixtures"]
    if mutation == "coverage": fixtures.pop()
    elif mutation == "unknown": fixtures[0]["schema_id"] = "unknown"
    elif mutation == "duplicate": fixtures[1]["fixture_id"] = "valid"
    else: fixtures[0]["expectation"] = "maybe"
    with pytest.raises(ContractValidationError): run_module(value)
