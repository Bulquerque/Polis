from importlib import import_module
from pathlib import Path
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "quant_pipeline.phase_00_zero_trust_guardian"

sys.path.insert(0, str(ROOT / "src"))
from ._material_p0_fixture_builder import MaterialP0FixtureBuilder


def test_phase_runner_executes_module_chain():
    from quant_pipeline.phase_00_zero_trust_guardian.modules import _p0_s7_utils
    input_contract = yaml.safe_load((ROOT / "contracts" / "INPUT_CONTRACTS.yaml").read_text(encoding="utf-8")) or {}
    required_inputs = input_contract.get("required_inputs", [])
    inputs = {name: {"source": name} for name in required_inputs}
    inputs["phase_registry_yaml"] = str(
        ROOT / "source_of_truth" / "registries" / "phase_registry.yaml"
    )
    inputs["global_architecture_config"] = {
        "authority": "global_master",
        "pipeline_version": "V14.1-RC4.1",
        "phase_registry_id": "phase_registry_v14_1_rc4_1",
    }
    inputs["subphase_registry_yaml"] = str(
        ROOT / "source_of_truth" / "registries" / "subphase_registry.yaml"
    )
    inputs["module_registry_yaml"] = str(
        ROOT / "source_of_truth" / "registries" / "module_registry.yaml"
    )
    inputs["connection_matrix_yaml"] = str(ROOT / "contracts" / "MODULE_IO_MATRIX.yaml")
    inputs["forbidden_connection_matrix_yaml"] = str(ROOT / "contracts" / "CONNECTIONS.yaml")
    workspace_root = ROOT.parents[1]
    inputs["module_io_matrix_all_phases"] = [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(workspace_root.glob("phase_*/**/contracts/MODULE_IO_MATRIX.yaml"))
    ]
    global_package = workspace_root / "global_contracts_parallel_agents" / "v14_1_global_contracts_parallel_agents_RC4_1"
    inputs["contracts_all_phases"] = str(
        global_package / "source_of_truth" / "registries" / "module_registry.yaml"
    )
    inputs["global_contracts"] = str(global_package / "contracts")
    runner = import_module(f"{PACKAGE}.runner")
    with tempfile.TemporaryDirectory(prefix="p0-material-") as scratch_name:
        scratch = Path(scratch_name)
        builder = MaterialP0FixtureBuilder(ROOT, scratch)
        _p0_s7_utils.REPOSITORY_ROOT = scratch
        inputs = builder.external_inputs()
        result = runner.run_phase(inputs, builder.config)
    assert result["phase"] == input_contract.get("phase")
    assert result["module_results"], "expected module results"
    output_contract = yaml.safe_load((ROOT / "contracts" / "OUTPUT_CONTRACTS.yaml").read_text(encoding="utf-8")) or {}
    for artifact in output_contract.get("outputs", []):
        assert artifact in result["phase_outputs"], artifact
        assert result["phase_outputs"][artifact] not in (None, ""), artifact
