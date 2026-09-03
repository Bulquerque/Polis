from importlib import import_module
from pathlib import Path
import sys

import pytest
import yaml

from quant_pipeline.phase_02_quality_pit.modules._module_executor import ContractValidationError

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "quant_pipeline.phase_02_quality_pit"
sys.path.insert(0, str(ROOT / "src"))


def test_phase_runner_rejects_unmaterialized_module_chain():
    input_contract = yaml.safe_load((ROOT / "contracts" / "INPUT_CONTRACTS.yaml").read_text(encoding="utf-8")) or {}
    inputs = {name: {"source": name} for name in input_contract.get("required_inputs", [])}
    runner = import_module(f"{PACKAGE}.runner")
    with pytest.raises(ContractValidationError, match="source|synthesized|records|materialized|provenance|missing"):
        runner.run_phase(inputs, {})

