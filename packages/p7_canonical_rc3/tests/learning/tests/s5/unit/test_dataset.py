import pytest
from quant_pipeline.phase_07_strategy_tournament.learning.domain.canonical import digest
from quant_pipeline.phase_07_strategy_tournament.learning.domain.errors import P7S5Error
from quant_pipeline.phase_07_strategy_tournament.learning.modules.P7_S5_M01_ranking_target_policy_registry_builder import run_module as run_m01
from quant_pipeline.phase_07_strategy_tournament.learning.modules.P7_S5_M02_counterfactual_training_dataset_builder import run_module as run_m02


def _inputs(input_bundle, config):
    registry = run_m01(input_bundle, config)["outputs"]["ranking_target_policy_registry"]
    return {
        "historical_tournament_snapshots": input_bundle["historical_tournament_snapshots"],
        "historical_candidate_counterfactual_outcome_panel": input_bundle["historical_candidate_counterfactual_outcome_panel"],
        "ranking_target_policy_registry": registry,
    }


def test_builds_counterfactual_dataset(input_bundle, config):
    result = run_m02(_inputs(input_bundle, config), config)
    assert result["metrics"] == {"row_count": 72, "query_count": 18}
    assert result["outputs"]["label_coverage_report"]["records"][-1]["coverage"] == 1.0


def test_rejects_selected_only_labels(input_bundle, config):
    inputs = _inputs(input_bundle, config)
    outcomes = inputs["historical_candidate_counterfactual_outcome_panel"]
    selected = {r["candidate_id"] for r in inputs["historical_tournament_snapshots"]["records"] if r["selected_by_p8"]}
    outcomes["records"] = [r for r in outcomes["records"] if r["candidate_id"] in selected]
    outcomes["record_count"] = len(outcomes["records"])
    outcomes["content_sha256"] = digest(outcomes["records"])
    config["dataset_policy"]["min_query_coverage"] = 0.0
    config["dataset_policy"]["min_overall_coverage"] = 0.0
    with pytest.raises(P7S5Error, match="P7_LTR_SELECTED_ONLY_LABELS"):
        run_m02(inputs, config)


def test_rejects_future_outcome(input_bundle, config):
    inputs = _inputs(input_bundle, config)
    outcomes = inputs["historical_candidate_counterfactual_outcome_panel"]
    outcomes["records"][0]["outcome_available_at"] = "2025-02-02T00:00:00Z"
    outcomes["content_sha256"] = digest(outcomes["records"])
    with pytest.raises(P7S5Error, match="P7_LTR_OUTCOME_FUTURE_DATED"):
        run_m02(inputs, config)


def test_rejects_future_feature(input_bundle, config):
    inputs = _inputs(input_bundle, config)
    snapshots = inputs["historical_tournament_snapshots"]
    snapshots["records"][0]["feature_available_at"] = "2025-01-03T20:00:00Z"
    snapshots["content_sha256"] = digest(snapshots["records"])
    with pytest.raises(P7S5Error, match="P7_LTR_FEATURE_FUTURE_DATED"):
        run_m02(inputs, config)
