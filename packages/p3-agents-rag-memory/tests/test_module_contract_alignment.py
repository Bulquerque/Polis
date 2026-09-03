from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE_DIR = ROOT / "src/quant_pipeline/phase_03_agents_rag_memory/modules"


def test_all_modules_share_canonical_metadata_entrypoint_and_contract_inputs():
    files = sorted(MODULE_DIR.glob("P3_S*_*.py"))
    assert len(files) == 81
    for path in files:
        module = importlib.import_module(
            f"quant_pipeline.phase_03_agents_rag_memory.modules.{path.stem}"
        )
        assert module.IMPLEMENTATION_STATUS == "IMPLEMENTED_QUALIFIED_INTERNAL"
        assert inspect.iscoroutinefunction(module.execute)
        contract_path = ROOT / module.CONTRACT
        assert contract_path.is_file()
        contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
        assert contract["module_id"] == module.MODULE_ID
        assert contract["module_name"] == module.MODULE_NAME
        assert contract["subphase"] == module.SUBPHASE
        assert tuple(contract["inputs"]) == tuple(module.REQUIRED_INPUTS)
        assert contract["implementation_status_policy"]["current"] == (
            "IMPLEMENTED_QUALIFIED_INTERNAL"
        )
        test_path = ROOT / contract["unit_test_target"]
        assert test_path.is_file() and test_path.suffix == ".py"
