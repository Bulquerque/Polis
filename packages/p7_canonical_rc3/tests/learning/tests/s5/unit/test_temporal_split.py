from quant_pipeline.phase_07_strategy_tournament.learning.runner_s5 import run_s5_pipeline


def test_folds_are_query_disjoint_and_test_sealed(input_bundle, config):
    result = run_s5_pipeline(input_bundle, config)
    folds = result["outputs"]["ltr_temporal_fold_plan"]["records"]
    assert len(folds) >= 2
    for fold in folds:
        train = set(fold["train_query_ids"])
        validation = set(fold["validation_query_ids"])
        calibration = set(fold["calibration_query_ids"])
        test = set(fold["sealed_test_query_ids"])
        assert not train & validation
        assert not train & calibration
        assert not train & test
        assert not validation & calibration
        assert not validation & test
        assert not calibration & test
        assert fold["test_sealed"] is True


def test_rejects_unsorted_calendar_and_insufficient_sessions(input_bundle, config):
    import copy
    import pytest
    from quant_pipeline.phase_07_strategy_tournament.learning.domain.canonical import digest
    from quant_pipeline.phase_07_strategy_tournament.learning.domain.errors import P7S5Error
    from quant_pipeline.phase_07_strategy_tournament.learning.modules.P7_S5_M01_ranking_target_policy_registry_builder import run_module as m01
    from quant_pipeline.phase_07_strategy_tournament.learning.modules.P7_S5_M02_counterfactual_training_dataset_builder import run_module as m02
    from quant_pipeline.phase_07_strategy_tournament.learning.modules.P7_S5_M03_query_group_temporal_split_planner import run_module as m03

    policies = m01(input_bundle, config)["outputs"]["ranking_target_policy_registry"]
    dataset = m02({
        "historical_tournament_snapshots": input_bundle["historical_tournament_snapshots"],
        "historical_candidate_counterfactual_outcome_panel": input_bundle["historical_candidate_counterfactual_outcome_panel"],
        "ranking_target_policy_registry": policies,
    }, config)["outputs"]["ltr_training_dataset_manifest"]
    calendar = copy.deepcopy(input_bundle["trading_calendar_reference"])
    calendar["records"][0]["sessions"] = list(reversed(calendar["records"][0]["sessions"]))
    calendar["content_sha256"] = digest(calendar["records"])
    with pytest.raises(P7S5Error, match="P7_LTR_CALENDAR_INVALID"):
        m03({"ltr_training_dataset_manifest": dataset, "trading_calendar_reference": calendar}, config)
    short = copy.deepcopy(config)
    short["split_policy"]["min_train_sessions"] = 30
    with pytest.raises(P7S5Error, match="P7_LTR_INSUFFICIENT_QUERIES"):
        m03({"ltr_training_dataset_manifest": dataset, "trading_calendar_reference": input_bundle["trading_calendar_reference"]}, short)
