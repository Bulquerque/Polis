import json
from pathlib import Path

from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.enums import ReasonCode


def test_reason_registry_matches_enum():
    root = Path(__file__).parents[1]
    registry = set(json.loads((root / "registries/s09/reason_codes.json").read_text()))
    assert registry == {item.value for item in ReasonCode}


def test_module_registry_has_five_unique_modules():
    root = Path(__file__).parents[1]
    registry = json.loads((root / "registries/s09/modules.json").read_text())
    ids = [item["id"] for item in registry["modules"]]
    assert len(ids) == len(set(ids)) == 5
    assert ids == [f"P8.S9.M0{i}" for i in range(1, 6)]
