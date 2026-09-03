from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = ROOT.parents[1]


def test_module_registry_has_four_ordered_modules():
    registry = yaml.safe_load((ROOT / "contracts/s4/MODULE_REGISTRY.yaml").read_text())
    assert [row["module_id"] for row in registry["modules"]] == ["P7.S4.M01", "P7.S4.M02", "P7.S4.M03", "P7.S4.M04"]


def test_each_module_contract_exists():
    registry = yaml.safe_load((ROOT / "contracts/s4/MODULE_REGISTRY.yaml").read_text())
    for row in registry["modules"]:
        assert (ROOT / "contracts/s4/modules" / Path(row["contract"]).name).is_file()
        assert (PACKAGE_ROOT / "src/quant_pipeline/phase_07_strategy_tournament/tournament/modules" / Path(row["source"]).name).is_file()
        assert (PACKAGE_ROOT / "src/quant_pipeline/phase_07_strategy_tournament/tournament" / Path(*Path(row["service"]).parts[3:])).is_file()
