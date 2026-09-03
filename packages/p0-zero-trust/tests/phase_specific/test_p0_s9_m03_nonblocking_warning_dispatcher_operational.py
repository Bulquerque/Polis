import pytest
from quant_pipeline.phase_00_zero_trust_guardian.modules._module_executor import ContractValidationError
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S9_M03_nonblocking_warning_dispatcher import run_module

L = "sha256:" + "b"*64
def panel():
    warning={"finding_id":"W1","phase_id":"P1","severity":"WARNING","message":"watch","owner":"team","action":"monitor","release_blocking":False}
    return {"artifact_id":"panel","lineage_id":L,"warning_count":1,"warnings":[warning]}
def test_dispatches_warning_without_blocking_release():
    report=run_module({"phase_zero_trust_feedback_panel":panel()})["outputs"]["nonblocking_warning_report"]
    assert report["status"] == "WARNING" and report["release_blocking"] is False
@pytest.mark.parametrize("mutation", ["owner","blocking","count"])
def test_rejects_invalid_warning_dispatch(mutation):
    value=panel()
    if mutation == "owner": value["warnings"][0]["owner"]=""
    elif mutation=="blocking": value["warnings"][0]["release_blocking"]=True
    else: value["warning_count"]=2
    with pytest.raises(ContractValidationError): run_module({"phase_zero_trust_feedback_panel":value})
