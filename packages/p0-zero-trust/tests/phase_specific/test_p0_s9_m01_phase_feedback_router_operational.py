import pytest
from quant_pipeline.phase_00_zero_trust_guardian.modules._module_executor import ContractValidationError
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S9_M01_phase_feedback_router import run_module

NAMES = ["release_gate_report", "phase_health_panel", "code_quality_report", "global_test_report"]
def payload():
    result = {}
    for n, name in enumerate(NAMES):
        phases = [{"phase_id": f"P{i}", "status": "PASS", "findings": []} for i in range(10)]
        result[name] = {"artifact_id": name, "lineage_id": "sha256:" + str(n) * 64, "phases": phases}
    result[NAMES[0]]["phases"][0] = {"phase_id": "P0", "status": "BLOCKED", "findings": [{"finding_id": "B1", "severity": "BLOCKING", "message": "broken", "owner": "team-a", "action": "fix"}]}
    result[NAMES[1]]["phases"][1] = {"phase_id": "P1", "status": "WARNING", "findings": [{"finding_id": "W1", "severity": "WARNING", "message": "watch", "owner": "team-b", "action": "monitor"}]}
    return result
def test_routes_all_phases_and_separates_severity():
    panel = run_module(payload(), {"created_at": "2026-01-01T00:00:00Z"})["outputs"]["phase_zero_trust_feedback_panel"]
    assert panel["phase_count"] == 10 and panel["blocking_count"] == 1 and panel["warning_count"] == 1 and panel["status"] == "BLOCKED"
@pytest.mark.parametrize("mutation", ["phase", "owner", "severity", "lineage", "duplicate"])
def test_rejects_untraceable_or_incomplete_feedback(mutation):
    value = payload()
    if mutation == "phase": value[NAMES[0]]["phases"].pop()
    elif mutation == "owner": value[NAMES[0]]["phases"][0]["findings"][0]["owner"] = ""
    elif mutation == "severity": value[NAMES[0]]["phases"][0]["findings"][0]["severity"] = "BOGUS"
    elif mutation == "lineage": value[NAMES[0]]["lineage_id"] = "fake"
    else: value[NAMES[1]]["phases"][1]["findings"][0]["finding_id"] = "B1"
    with pytest.raises(ContractValidationError): run_module(value)
