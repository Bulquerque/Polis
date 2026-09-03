import copy
from quant_pipeline.phase_07_strategy_tournament.learning.domain.canonical import digest
from quant_pipeline.phase_07_strategy_tournament.learning.runner_s5 import run_s5_pipeline


def test_unused_future_query_does_not_change_prior_model(input_bundle, config):
    first = run_s5_pipeline(copy.deepcopy(input_bundle), copy.deepcopy(config))
    model_hashes = [row["model_hash"] for row in first["outputs"]["ltr_model_artifact"]["records"]]
    # Add an unrelated record after the training cutoff; M02 must reject rather than contaminate.
    future = copy.deepcopy(input_bundle)
    future_row = copy.deepcopy(future["historical_candidate_counterfactual_outcome_panel"]["records"][0])
    future_row["candidate_id"] = "not-in-snapshot"
    future_row["query_id"] = "future-query"
    future["historical_candidate_counterfactual_outcome_panel"]["records"].append(future_row)
    future["historical_candidate_counterfactual_outcome_panel"]["record_count"] += 1
    future["historical_candidate_counterfactual_outcome_panel"]["content_sha256"] = digest(future["historical_candidate_counterfactual_outcome_panel"]["records"])
    from quant_pipeline.phase_07_strategy_tournament.learning.domain.errors import P7S5Error
    import pytest
    with pytest.raises(P7S5Error):
        run_s5_pipeline(future, copy.deepcopy(config))
    assert model_hashes
