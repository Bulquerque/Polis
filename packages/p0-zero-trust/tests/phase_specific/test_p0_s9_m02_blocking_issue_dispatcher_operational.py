import copy
import pytest
from quant_pipeline.phase_00_zero_trust_guardian.modules._module_executor import ContractValidationError
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S9_M02_blocking_issue_dispatcher import run_module

L = "sha256:" + "a"*64
def panel():
    issue = {"finding_id":"B1","phase_id":"P0","severity":"BLOCKING","message":"broken","owner":"team","action":"fix","release_blocking":True}
    return {"artifact_id":"panel","lineage_id":L,"blocking_count":1,"blocking_errors":[issue]}
def test_dispatches_blocker_with_owner_and_action():
    report=run_module({"phase_zero_trust_feedback_panel":panel()})["outputs"]["blocking_issue_report"]
    assert report["status"] == "BLOCKED" and report["issues"][0]["dispatch_status"] == "ROUTED" and report["issues"][0]["external_dispatch_performed"] is False
@pytest.mark.parametrize("mutation", ["owner","action","severity","count"])
def test_rejects_invalid_blocker_dispatch(mutation):
    value=panel()
    if mutation in {"owner","action"}: value["blocking_errors"][0][mutation]=""
    elif mutation=="severity": value["blocking_errors"][0]["severity"]="WARNING"
    else: value["blocking_count"]=2
    with pytest.raises(ContractValidationError): run_module({"phase_zero_trust_feedback_panel":value})
