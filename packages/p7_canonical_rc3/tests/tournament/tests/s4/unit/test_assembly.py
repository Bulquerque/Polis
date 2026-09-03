from __future__ import annotations

import math

from quant_pipeline.phase_07_strategy_tournament.tournament.s4_runner import run_subphase

from tests.tournament.tests.s4.factories import execution_config, make_bundle, scoring_policy, scoring_rule


def _scores(bundle):
    return run_subphase(bundle, execution_config())["outputs"]["interpretable_score_panel"]["records"]


def _lookup(records, candidate):
    return next(row for row in records if row["candidate_id"] == candidate)


def test_known_numeric_fixture():
    scores = _scores(make_bundle())
    assert math.isclose(_lookup(scores, "A")["base_score"], 0.5975)
    assert math.isclose(_lookup(scores, "A")["final_interpretable_score"], 0.5825625)


def test_head_contributions_reconcile_base_score():
    for score in _scores(make_bundle()):
        assert math.isclose(sum(row["weighted_contribution"] for row in score["head_contributions"]), score["base_score"])


def test_confidence_shrinkage_never_increases_score():
    for score in _scores(make_bundle()):
        assert score["confidence_adjustment"] <= 0.0
        assert score["final_interpretable_score"] <= score["base_score"]


def test_lower_confidence_causes_larger_shrinkage():
    scores = _scores(make_bundle())
    assert abs(_lookup(scores, "C")["confidence_adjustment"]) > abs(_lookup(scores, "A")["confidence_adjustment"])


def test_penalty_is_applied_below_threshold():
    scores = _scores(make_bundle(value_overrides={("A", "expected_shortfall"): -19.0}))
    row = _lookup(scores, "A")
    assert row["penalty_total"] > 0.0
    assert any(item["penalty_id"] == "downside-floor" and item["penalty_value"] > 0 for item in row["applied_penalties"])


def test_missing_blocking_head_blocks_candidate_score():
    row = _lookup(_scores(make_bundle(missing_metric=("A", "robustness_confidence"))), "A")
    assert row["score_status"] == "BLOCKED"
    assert row["final_interpretable_score"] is None


def test_no_ltr_rank_or_portfolio_fields():
    text = str(_scores(make_bundle())).lower()
    assert "ltr_score" not in text
    assert "portfolio_weight" not in text
    assert "'rank'" not in text


def test_zero_confidence_strength_disables_adjustment():
    policy = scoring_policy(rules=(scoring_rule(confidence_strength=0.0),))
    for score in _scores(make_bundle(policy=policy)):
        assert score["confidence_adjustment"] == 0.0
