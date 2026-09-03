from importlib import import_module
from pathlib import Path
import json
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "quant_pipeline.phase_00_zero_trust_guardian.modules"
VALID_ARCHITECTURE = {
    "authority": "global_master",
    "pipeline_version": "V14.1-RC4.1",
    "phase_registry_id": "phase_registry_v14_1_rc4_1",
}

sys.path.insert(0, str(ROOT / "src"))
from ._material_p0_fixture_builder import MaterialP0FixtureBuilder


def _validated_s1_registries():
    phase_registry = import_module(f"{PACKAGE}.P0_S1_M01_phase_registry_loader").run_module(
        {
            "phase_registry_yaml": str(ROOT / "source_of_truth" / "registries" / "phase_registry.yaml"),
            "global_architecture_config": VALID_ARCHITECTURE,
        },
        {},
    )["outputs"]["validated_phase_registry"]
    subphase_registry = import_module(f"{PACKAGE}.P0_S1_M02_subphase_registry_loader").run_module(
        {
            "validated_phase_registry": phase_registry,
            "subphase_registry_yaml": str(ROOT / "source_of_truth" / "registries" / "subphase_registry.yaml"),
        },
        {},
    )["outputs"]["validated_subphase_registry"]
    module_registry = import_module(f"{PACKAGE}.P0_S1_M03_module_registry_loader").run_module(
        {
            "validated_phase_registry": phase_registry,
            "validated_subphase_registry": subphase_registry,
            "module_registry_yaml": str(ROOT / "source_of_truth" / "registries" / "module_registry.yaml"),
        },
        {},
    )["outputs"]["validated_module_registry"]
    return phase_registry, subphase_registry, module_registry


def _all_io_matrices():
    workspace_root = ROOT.parents[1]
    paths = sorted(workspace_root.glob("phase_*/**/contracts/MODULE_IO_MATRIX.yaml"))
    return [yaml.safe_load(path.read_text(encoding="utf-8")) for path in paths]


def test_all_module_wrappers_load_and_execute():
    from quant_pipeline.phase_00_zero_trust_guardian import runner
    from quant_pipeline.phase_00_zero_trust_guardian.modules import _p0_s7_utils
    with tempfile.TemporaryDirectory(prefix="p0-material-") as scratch_name:
        scratch = Path(scratch_name)
        builder = MaterialP0FixtureBuilder(ROOT, scratch)
        _p0_s7_utils.REPOSITORY_ROOT = scratch
        phase_result = runner.run_phase(builder.external_inputs(), builder.config)
    results = {result["module_id"]: result for result in phase_result["module_results"]}
    contract_files = sorted((ROOT / "modules").glob("*.yaml"))
    assert contract_files, "no module contracts found"

    for contract_file in contract_files:
        spec = yaml.safe_load(contract_file.read_text(encoding="utf-8")) or {}
        result = results[spec["module_id"]]
        assert result["module_id"] == spec["module_id"]
        assert result["module_name"] == spec["module_name"]
        assert sorted(result["outputs"]) == sorted(spec.get("outputs", []))
        payload = json.dumps(result["outputs"], sort_keys=True, default=str)
        assert "::" not in payload
        for artifact, record in result["outputs"].items():
            schema = yaml.safe_load((ROOT / "schemas" / f"{artifact}.schema.yaml").read_text(encoding="utf-8")) or {}
            for field in schema.get("required_fields", []):
                assert field in record, (artifact, field)
                assert record[field] not in (None, ""), (artifact, field)
            for field in schema.get("forbidden_fields", []):
                assert field not in record, (artifact, field)
        continue
        inputs = {name: {"source": name} for name in spec.get("inputs", [])}
        if spec.get("module_id") == "P0.S1.M01":
            inputs["phase_registry_yaml"] = str(
                ROOT / "source_of_truth" / "registries" / "phase_registry.yaml"
            )
            inputs["global_architecture_config"] = VALID_ARCHITECTURE
        elif spec.get("module_id") in {"P0.S1.M02", "P0.S1.M03", "P0.S1.M04", "P0.S1.M05"}:
            phase_registry, subphase_registry, module_registry = _validated_s1_registries()
            if spec.get("module_id") == "P0.S1.M02":
                inputs = {
                    "validated_phase_registry": phase_registry,
                    "subphase_registry_yaml": str(ROOT / "source_of_truth" / "registries" / "subphase_registry.yaml"),
                }
            elif spec.get("module_id") == "P0.S1.M03":
                inputs = {
                    "validated_phase_registry": phase_registry,
                    "validated_subphase_registry": subphase_registry,
                    "module_registry_yaml": str(ROOT / "source_of_truth" / "registries" / "module_registry.yaml"),
                }
            elif spec.get("module_id") == "P0.S1.M04":
                inputs = {
                    "connection_matrix_yaml": str(ROOT / "contracts" / "MODULE_IO_MATRIX.yaml"),
                    "validated_phase_registry": phase_registry,
                    "validated_module_registry": module_registry,
                }
            else:
                validated_matrix = import_module(f"{PACKAGE}.P0_S1_M04_connection_matrix_validator").run_module(
                    {
                        "connection_matrix_yaml": str(ROOT / "contracts" / "MODULE_IO_MATRIX.yaml"),
                        "validated_phase_registry": phase_registry,
                        "validated_module_registry": module_registry,
                    },
                    {},
                )["outputs"]["validated_connection_matrix"]
                inputs = {
                    "validated_connection_matrix": validated_matrix,
                    "forbidden_connection_matrix_yaml": str(ROOT / "contracts" / "CONNECTIONS.yaml"),
                    "module_io_matrix_all_phases": _all_io_matrices(),
                }
        elif spec.get("module_id") == "P0.S2.M01":
            workspace_root = ROOT.parents[1]
            global_package = workspace_root / "global_contracts_parallel_agents" / "v14_1_global_contracts_parallel_agents_RC4_1"
            inputs = {
                "contracts_all_phases": str(global_package / "source_of_truth" / "registries" / "module_registry.yaml"),
                "global_contracts": str(global_package / "contracts"),
            }
        result = module.run_module(inputs, {})
        assert result["module_id"] == spec["module_id"]
        assert result["module_name"] == spec["module_name"]
        assert sorted(result["outputs"]) == sorted(spec.get("outputs", []))
        payload = json.dumps(result["outputs"], sort_keys=True, default=str)
        assert "::" not in payload
        for artifact, record in result["outputs"].items():
            schema = yaml.safe_load((ROOT / "schemas" / f"{artifact}.schema.yaml").read_text(encoding="utf-8")) or {}
            for field in schema.get("required_fields", []):
                assert field in record, (artifact, field)
                assert record[field] not in (None, ""), (artifact, field)
            for field in schema.get("forbidden_fields", []):
                assert field not in record, (artifact, field)
