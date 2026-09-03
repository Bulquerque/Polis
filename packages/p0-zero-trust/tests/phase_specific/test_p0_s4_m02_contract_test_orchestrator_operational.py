import copy
import pytest

from quant_pipeline.phase_00_zero_trust_guardian.modules._module_executor import ContractValidationError
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S4_M02_contract_test_orchestrator import run_module


def payload():
    contract = {"module_id": "P0.S1.M01", "inputs": ["a"], "outputs": ["b"], "consumes_from": {"modules": [], "artifacts": ["a"]}, "emits_to": {"modules": [], "artifacts": ["b"]}, "output_schemas": [{"artifact": "b", "schema_path": "schemas/b.schema.yaml"}]}
    return {"contract_registry": {"contracts": [contract]}, "schema_registry": {"schemas": [{"schema_id": "b.v1", "path": "schemas/b.schema.yaml"}]}, "validated_module_registry": {"modules": [{"module_id": "P0.S1.M01"}]}}


def test_executes_material_contract_checks():
    outputs = run_module(payload(), {"created_at": "2026-01-01T00:00:00Z"})["outputs"]
    assert outputs["contract_test_report"]["status"] == "PASS"
    assert outputs["contract_test_execution_plan"]["test_count"] == 4


@pytest.mark.parametrize("mutation", ["identity", "schema", "io", "forbidden"])
def test_fails_closed_on_registry_gaps(mutation):
    value = payload()
    if mutation == "identity": value["validated_module_registry"]["modules"][0]["module_id"] = "P9.S9.M9"
    elif mutation == "schema": value["schema_registry"]["schemas"].clear()
    elif mutation == "io": value["contract_registry"]["contracts"][0].pop("inputs")
    else: value["target"] = "leak"
    with pytest.raises(ContractValidationError): run_module(value)
