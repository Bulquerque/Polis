from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = ROOT.parents[1]


def test_module_registry_matches_implementation_files():
    registry = yaml.safe_load((ROOT / "contracts/s3/MODULE_REGISTRY.yaml").read_text(encoding="utf-8"))
    assert [row["module_id"] for row in registry["modules"]] == [
        "P7.S3.M01",
        "P7.S3.M02",
        "P7.S3.M03",
        "P7.S3.M04",
    ]
    for row in registry["modules"]:
        assert (PACKAGE_ROOT / "src/quant_pipeline/phase_07_strategy_tournament/tournament/modules" / Path(row["source"]).name).is_file()
        assert (PACKAGE_ROOT / "src/quant_pipeline/phase_07_strategy_tournament/tournament" / Path(*Path(row["service"]).parts[3:])).is_file()


def test_no_ranking_or_portfolio_output_is_declared():
    contract = yaml.safe_load((ROOT / "contracts/s3/OUTPUT_CONTRACTS.yaml").read_text(encoding="utf-8"))
    forbidden = {"rank", "top_k", "recommended_trade", "ltr_score", "portfolio_weight", "execution_order"}
    assert forbidden.isdisjoint(contract["outputs"])
