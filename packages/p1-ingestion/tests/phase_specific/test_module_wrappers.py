from importlib import import_module
from pathlib import Path
import sys

import pytest
import yaml

from quant_pipeline.phase_01_ingestion.modules._module_executor import ContractValidationError

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "quant_pipeline.phase_01_ingestion.modules"
sys.path.insert(0, str(ROOT / "src"))


def test_all_module_wrappers_reject_unmaterialized_sources():
    contract_files = sorted((ROOT / "modules").glob("*.yaml"))
    assert contract_files
    for contract_file in contract_files:
        spec = yaml.safe_load(contract_file.read_text(encoding="utf-8")) or {}
        module = import_module(f"{PACKAGE}.{contract_file.stem}")
        inputs = {name: {"source": name} for name in spec.get("inputs", [])}
        with pytest.raises(ContractValidationError, match="source|synthesized|records|materialized|provenance|missing"):
            module.run_module(inputs, {})

