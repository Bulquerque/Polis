from __future__ import annotations

import math

from quant_pipeline.phase_07_strategy_tournament.tournament.s4_runner import run_subphase

from tests.tournament.tests.s4.factories import execution_config, make_bundle


def _result(bundle):
    return run_subphase(bundle, execution_config())["outputs"]


def test_permutation_invariance_of_economic_records():
    first = _result(make_bundle())
    second = _result(make_bundle(reverse_records=True))
    assert first["scoring_head_panel"]["records"] == second["scoring_head_panel"]["records"]
    assert first["interpretable_score_panel"]["records"] == second["interpretable_score_panel"]["records"]
    def economic(rows):
        return [{key: value for key, value in row.items() if key != "source_artifact_id"} for row in rows]
    assert economic(first["score_decomposition_panel"]["records"]) == economic(second["score_decomposition_panel"]["records"])


def test_increasing_belief_fit_cannot_reduce_belief_head():
    base = _result(make_bundle())
    raised = _result(make_bundle(value_overrides={("A", "belief_fit"): 0.95}))
    def head(outputs):
        return next(row for row in outputs["scoring_head_panel"]["records"] if row["candidate_id"] == "A" and row["head_id"] == "BELIEF_FIT")["head_score"]
    assert head(raised) >= head(base)


def test_metric_contributions_sum_to_each_head():
    outputs = _result(make_bundle())
    for head in outputs["scoring_head_panel"]["records"]:
        if head["head_score"] is None:
            continue
        total = sum(row["contribution"] for row in head["stages"] if row["normalized_value"] is not None)
        assert math.isclose(total / head["effective_metric_weight"], head["head_score"])


def test_score_records_preserve_input_order_independence():
    first = _result(make_bundle())["interpretable_score_panel"]["records"]
    second = _result(make_bundle(reverse_records=True))["interpretable_score_panel"]["records"]
    assert first == second
