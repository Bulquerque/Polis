from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S7_M03_agent_execution_policy_builder import ContractValidationError, run_module

def valid():
    return {"validated_agent_prompt_templates": {"artifact_id": "validated-prompts-" + "a" * 12, "lineage_id": "sha256:" + "a" * 64, "pipeline_version": "V14.1-RC4.1", "status": "PASS", "release_blocking": False, "templates": [{"template_id": "audit-v1"}]}, "code_standards": {"definition_of_done": ["tests pass", "evidence recorded"], "permissions": {"read": True, "write": False}}, "testing_standards": {"required_tests": ["unit", "adversarial"], "required_package_files": ["SKILL.md", "tests/test_skill.py"]}}

def test_builds_material_execution_policy():
    out = run_module(valid(), {"created_at": "2026-07-19T00:00:00Z"})["outputs"]["agent_execution_policy"]
    assert out["status"] == "PASS" and out["permissions"]["write"] is False and out["required_tests"] == ["unit", "adversarial"]

@pytest.mark.parametrize("field", ["definition_of_done", "required_tests", "permissions"])
def test_rejects_incomplete_policy(field):
    data = valid()
    if field == "definition_of_done": data["code_standards"][field] = []
    elif field == "required_tests": data["testing_standards"][field] = []
    else: data["code_standards"][field] = {"root": True}
    with pytest.raises(ContractValidationError): run_module(data)

@pytest.mark.parametrize("mutation", ["status", "version", "lineage"])
def test_rejects_untrusted_prompt_artifact(mutation):
    data = valid(); upstream = data["validated_agent_prompt_templates"]
    if mutation == "status": upstream["status"] = "FAIL"; upstream["release_blocking"] = True
    elif mutation == "version": upstream["pipeline_version"] = "OLD"
    else: upstream["lineage_id"] = "sha256:" + "b" * 64
    with pytest.raises(ContractValidationError): run_module(data)
