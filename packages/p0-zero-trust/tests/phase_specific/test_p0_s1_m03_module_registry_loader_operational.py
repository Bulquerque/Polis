from copy import deepcopy
from importlib import import_module
from pathlib import Path
import hashlib
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ROOT.parents[1]
GLOBAL_REGISTRY = (
    REPOSITORY_ROOT
    / "global_contracts_parallel_agents"
    / "v14_1_global_contracts_parallel_agents_RC4_1"
    / "source_of_truth"
    / "registries"
    / "module_registry.yaml"
)
P0_REGISTRY = ROOT / "source_of_truth" / "registries" / "module_registry.yaml"
PACKAGE = "quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S1_M03_module_registry_loader"

sys.path.insert(0, str(ROOT / "src"))
module = import_module(PACKAGE)


def _registry():
    return yaml.safe_load(GLOBAL_REGISTRY.read_text(encoding="utf-8"))


def _validated_parents(registry):
    phase_ids = sorted({item["phase_id"] for item in registry["modules"]}, key=lambda value: int(value[1:]))
    subphase_pairs = sorted(
        {(item["subphase_id"], item["phase_id"]) for item in registry["modules"]},
        key=lambda pair: tuple(int(part[1:]) for part in pair[0].split(".")),
    )
    return (
        {"phases": [{"phase_id": phase_id} for phase_id in phase_ids]},
        {
            "subphases": [
                {"subphase_id": subphase_id, "phase_id": phase_id}
                for subphase_id, phase_id in subphase_pairs
            ]
        },
    )


def _inputs(registry_value=None):
    registry = _registry()
    phases, subphases = _validated_parents(registry)
    return {
        "validated_phase_registry": phases,
        "validated_subphase_registry": subphases,
        "module_registry_yaml": GLOBAL_REGISTRY if registry_value is None else registry_value,
    }


def test_canonical_registry_covers_the_current_real_hashed_contract_inventory():
    assert GLOBAL_REGISTRY.read_bytes() == P0_REGISTRY.read_bytes()
    registry = _registry()
    modules = registry["modules"]
    assert registry["registry_id"] == "module_registry_v14_1_rc4_1"
    assert registry["hash_algorithm"] == "sha256"
    assert registry["module_count"] == len(modules)
    assert len({item["module_id"] for item in modules}) == len(modules)
    assert len({item["contract_path"] for item in modules}) == len(modules)
    assert len({item["subphase_id"] for item in modules}) == len(set(item["subphase_id"] for item in modules))
    for item in modules:
        contract = REPOSITORY_ROOT / item["contract_path"]
        assert contract.is_file(), item["module_id"]
        assert hashlib.sha256(contract.read_bytes()).hexdigest() == item["contract_sha256"]
        spec = yaml.safe_load(contract.read_text(encoding="utf-8"))
        assert spec["module_id"] == item["module_id"]
        assert spec["module_name"] == item["module_name"]
        assert spec["subphase"] == item["subphase_id"]


def test_m03_accepts_real_path_and_emits_verified_registry():
    result = module.run_module(
        _inputs(),
        {"pipeline_version": "V14.1-RC4.1", "created_at": "2026-07-19T00:00:00Z"},
    )
    artifact = result["outputs"]["validated_module_registry"]
    assert result["module_id"] == "P0.S1.M03"
    assert artifact["module_count"] == len(artifact["modules"])
    assert artifact["module_id_unique"] is True
    assert artifact["module_has_contract"] is True
    assert artifact["module_parent_valid"] is True
    assert artifact["contract_identity_valid"] is True
    assert artifact["contract_hash_valid"] is True
    assert artifact["promotion_blocked"] is True
    assert artifact["validation_evidence_status"] == "domain_oracle_pass_pending_independent_judge"


def test_m03_accepts_inline_real_registry_deterministically():
    registry = _registry()
    config = {"pipeline_version": "V14.1-RC4.1", "created_at": "2026-07-19T00:00:00Z"}
    first = module.run_module(_inputs(deepcopy(registry)), config)
    second = module.run_module(_inputs(deepcopy(registry)), config)
    first_artifact = first["outputs"]["validated_module_registry"]
    second_artifact = second["outputs"]["validated_module_registry"]
    assert first_artifact == second_artifact
    assert first_artifact["source_path"] == "inline:module_registry_yaml"


def test_m03_rejects_duplicate_module_identity():
    registry = _registry()
    registry["modules"][-1] = deepcopy(registry["modules"][0])
    with pytest.raises(ValueError, match="module_id_unique"):
        module.run_module(_inputs(registry), {})


def test_m03_rejects_unknown_parent_subphase():
    registry = _registry()
    registry["modules"][0]["subphase_id"] = "P0.S999"
    with pytest.raises(ValueError, match="parent subphase is invalid"):
        module.run_module(_inputs(registry), {})


def test_m03_rejects_contract_outside_repository():
    registry = _registry()
    registry["modules"][0]["contract_path"] = "../outside.yaml"
    with pytest.raises(ValueError, match="escapes repository authority"):
        module.run_module(_inputs(registry), {})


def test_m03_rejects_contract_identity_and_hash_tampering():
    identity_registry = _registry()
    identity_registry["modules"][0]["module_name"] = "tampered_name"
    with pytest.raises(ValueError, match="filename identity mismatch"):
        module.run_module(_inputs(identity_registry), {})

    hash_registry = _registry()
    hash_registry["modules"][0]["contract_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="contract hash mismatch"):
        module.run_module(_inputs(hash_registry), {})


def test_m03_rejects_nested_forbidden_fields():
    inputs = _inputs()
    inputs["validated_subphase_registry"]["subphases"][0]["nested"] = {
        "future_return": 1.0
    }
    with pytest.raises(ValueError, match="forbidden input fields"):
        module.run_module(inputs, {})
