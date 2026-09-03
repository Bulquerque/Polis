from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S7_M01_agent_skill_registry_builder import ContractValidationError, run_module

def valid():
    return {"agent_skill_definitions_yaml": {"skills": [{"skill_id": "audit", "phase_scope": "P0", "module_scope": ["P0.S7.M01"], "permissions": ["read"], "allowed_paths": ["reports/"]}]}, "validated_phase_registry": {"phases": [{"phase_id": "P0"}]}, "validated_module_registry": {"modules": [{"module_id": "P0.S7.M01"}]}}

def test_builds_material_registry_with_permissions_and_hash():
    out = run_module(valid(), {"created_at": "2026-07-19T00:00:00Z"})["outputs"]["agent_skill_registry"]
    assert out["status"] == "PASS" and out["skill_count"] == 1 and len(out["source_sha256"]) == 64

@pytest.mark.parametrize("mutation", ["permission", "module", "path"])
def test_rejects_invalid_authority(mutation):
    data = valid(); skill = data["agent_skill_definitions_yaml"]["skills"][0]
    if mutation == "permission": skill["permissions"] = ["root"]
    elif mutation == "module": skill["module_scope"] = ["P9.BAD"]
    else: skill["allowed_paths"] = ["../secret"]
    with pytest.raises(ContractValidationError): run_module(data)

@pytest.mark.parametrize("mutation", ["status", "version", "lineage"])
def test_rejects_untrusted_registry_artifact(mutation):
    data = valid(); upstream = data["validated_phase_registry"]
    upstream.update({"artifact_id": "validated-phase-registry-" + "d" * 12, "lineage_id": "sha256:" + "d" * 64, "pipeline_version": "V14.1-RC4.1", "status": "PASS", "release_blocking": False})
    if mutation == "status": upstream["status"] = "FAIL"; upstream["release_blocking"] = True
    elif mutation == "version": upstream["pipeline_version"] = "OLD"
    else: upstream["lineage_id"] = "sha256:" + "e" * 64
    with pytest.raises(ContractValidationError): run_module(data)
