from copy import deepcopy
from importlib import import_module
from pathlib import Path
import hashlib
import shutil
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ROOT.parents[1]
GLOBAL_PACKAGE_ROOT = (
    REPOSITORY_ROOT
    / "global_contracts_parallel_agents"
    / "v14_1_global_contracts_parallel_agents_RC4_1"
)
MODULE_REGISTRY = GLOBAL_PACKAGE_ROOT / "source_of_truth" / "registries" / "module_registry.yaml"
GLOBAL_CONTRACTS = GLOBAL_PACKAGE_ROOT / "contracts"
PACKAGE = "quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S2_M01_contract_registry_builder"

sys.path.insert(0, str(ROOT / "src"))
module = import_module(PACKAGE)


def _manifest():
    return yaml.safe_load(MODULE_REGISTRY.read_text(encoding="utf-8"))


def _inputs(contracts=None, global_contracts=None):
    return {
        "contracts_all_phases": MODULE_REGISTRY if contracts is None else contracts,
        "global_contracts": GLOBAL_CONTRACTS if global_contracts is None else global_contracts,
    }


def _run(inputs=None):
    return module.run_module(
        _inputs() if inputs is None else inputs,
        {"pipeline_version": "V14.1-RC4.1", "created_at": "2026-07-19T00:00:00Z"},
    )["outputs"]["contract_registry"]


def test_s2_m01_builds_registry_from_all_real_contracts():
    artifact = _run()
    assert artifact["contract_count"] == len(artifact["contracts"]) == 268
    assert artifact["global_contract_count"] == len(artifact["global_contracts"]) == 17
    assert len({item["contract_id"] for item in artifact["contracts"]}) == 268
    assert len({item["contract_path"] for item in artifact["contracts"]}) == 268
    assert len({item["contract_sha256"] for item in artifact["contracts"]}) == 268
    assert sum(len(item["outputs"]) for item in artifact["contracts"]) == 405
    assert sum(len(item["artifacts"]) for item in artifact["global_contracts"]) == 93
    assert artifact["contract_has_source_target"] is True
    assert artifact["shared_artifacts_have_schema"] is True
    assert artifact["contract_identity_valid"] is True
    assert artifact["contract_hash_valid"] is True
    assert artifact["connection_graph_valid"] is True
    assert artifact["promotion_blocked"] is True
    for contract in artifact["contracts"]:
        path = REPOSITORY_ROOT / contract["contract_path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == contract["contract_sha256"]
        assert len(contract["outputs"]) == len(contract["output_schemas"])
        for schema in contract["output_schemas"]:
            assert (REPOSITORY_ROOT / schema["schema_path"]).is_file()


def test_s2_m01_accepts_inline_manifest_deterministically():
    manifest = _manifest()
    first = _run(_inputs(deepcopy(manifest)))
    second = _run(_inputs(deepcopy(manifest)))
    assert first == second
    assert first["contracts_source_path"] == "inline:contracts_all_phases"


def test_s2_m01_rejects_malformed_contract_manifest():
    with pytest.raises(ValueError, match="must contain exactly 166 entries"):
        _run(
            _inputs(
                {
                    "registry_id": "module_registry_v14_1_rc4_1",
                    "hash_algorithm": "sha256",
                    "module_count": 166,
                    "modules": [],
                }
            )
        )


@pytest.mark.parametrize("field", ["module_id", "contract_path", "contract_sha256"])
def test_s2_m01_rejects_duplicate_contract_identity_path_or_hash(field):
    manifest = _manifest()
    manifest["modules"][1][field] = manifest["modules"][0][field]
    expected = {
        "module_id": "contract IDs must be unique",
        "contract_path": "contract paths must be present and unique",
        "contract_sha256": "contract hashes must be unique",
    }[field]
    with pytest.raises(ValueError, match=expected):
        _run(_inputs(manifest))


def test_s2_m01_rejects_missing_output_schema(monkeypatch, tmp_path):
    missing = tmp_path / "missing.schema.yaml"
    monkeypatch.setattr(module, "_schema_for_output", lambda _contract, _artifact: missing)
    with pytest.raises(ValueError, match="missing output schema"):
        _run()


def test_s2_m01_rejects_internal_path_escape_and_hash_tampering():
    escaped = _manifest()
    escaped["modules"][0]["contract_path"] = "../outside.yaml"
    with pytest.raises(ValueError, match="escapes repository authority"):
        _run(_inputs(escaped))

    tampered = _manifest()
    tampered["modules"][0]["contract_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="module contract hash mismatch"):
        _run(_inputs(tampered))


def test_s2_m01_rejects_malformed_global_contract(monkeypatch, tmp_path):
    copied = tmp_path / "contracts"
    shutil.copytree(GLOBAL_CONTRACTS, copied)
    (copied / "phase_00_to_all_governance.yaml").write_text(
        "shared_artifacts: [", encoding="utf-8"
    )
    monkeypatch.setattr(module, "GLOBAL_CONTRACT_ROOT", copied)
    with pytest.raises(ValueError, match="malformed YAML for global contract"):
        _run(_inputs(global_contracts=copied))


def test_s2_m01_rejects_nested_forbidden_fields():
    inputs = _inputs()
    inputs["global_contracts"] = {
        "path": str(GLOBAL_CONTRACTS),
        "metadata": {"nested": [{"target": "leak"}]},
    }
    with pytest.raises(ValueError, match="forbidden input fields"):
        _run(inputs)
