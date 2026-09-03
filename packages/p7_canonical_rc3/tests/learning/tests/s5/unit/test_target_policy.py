from quant_pipeline.phase_07_strategy_tournament.learning.modules.P7_S5_M01_ranking_target_policy_registry_builder import run_module
from quant_pipeline.phase_07_strategy_tournament.learning.domain.errors import P7S5Error
import pytest


def test_compiles_target_policy(input_bundle, config):
    result = run_module(input_bundle, config)
    record = result["outputs"]["ranking_target_policy_registry"]["records"][0]
    assert record["utility_multiplier"] == 1.0
    assert len(record["semantic_hash"]) == 64


def test_rejects_unit_mismatch(input_bundle, config):
    source = input_bundle["ranking_target_policy_source"]
    source["records"][0]["unit"] = "return"
    from quant_pipeline.phase_07_strategy_tournament.learning.domain.canonical import digest
    source["content_sha256"] = digest(source["records"])
    with pytest.raises(P7S5Error, match="P7_LTR_TARGET_UNIT_MISMATCH"):
        run_module(input_bundle, config)
