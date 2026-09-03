from __future__ import annotations

from quant_pipeline.phase_07_strategy_tournament.tournament.modules.P7_S4_M01_scoring_policy_head_binding_compiler import run_module as bind
from quant_pipeline.phase_07_strategy_tournament.tournament.modules.P7_S4_M02_multi_head_score_engine import run_module as score

from tests.tournament.tests.s4.factories import execution_config, make_bundle, scoring_policy, scoring_rule
from quant_pipeline.phase_07_strategy_tournament.tournament.domain.enums import MissingMetricAction, SmallGroupAction


def _run(bundle):
    bound = bind(bundle, execution_config())["outputs"]
    inputs = {**bundle, **bound}
    return score(inputs, execution_config())["outputs"]["scoring_head_panel"]["records"]


def _lookup(records, candidate, head):
    return next(row for row in records if row["candidate_id"] == candidate and row["head_id"] == head)


def test_multi_head_scores_are_bounded():
    records = _run(make_bundle())
    assert len(records) == 14
    assert all(row["head_score"] is None or 0.0 <= row["head_score"] <= 1.0 for row in records)


def test_percentile_edge_is_monotonic():
    records = _run(make_bundle())
    assert _lookup(records, "C", "ECONOMIC_EDGE")["head_score"] > _lookup(records, "A", "ECONOMIC_EDGE")["head_score"]


def test_downside_head_respects_directed_metric():
    records = _run(make_bundle())
    assert _lookup(records, "A", "DOWNSIDE_SAFETY")["head_score"] > _lookup(records, "C", "DOWNSIDE_SAFETY")["head_score"]


def test_small_group_uses_absolute_fallback():
    records = _run(make_bundle(separate_c_group=True))
    assert _lookup(records, "A", "ECONOMIC_EDGE")["head_score"] == 0.6
    assert _lookup(records, "C", "ECONOMIC_EDGE")["head_score"] == 0.75


def test_small_group_can_be_explicitly_unavailable():
    policy = scoring_policy(rules=(scoring_rule(small_group=SmallGroupAction.UNAVAILABLE),))
    records = _run(make_bundle(separate_c_group=True, policy=policy))
    assert _lookup(records, "A", "ECONOMIC_EDGE")["head_status"] == "BLOCKED"


def test_missing_required_metric_blocks_head():
    records = _run(make_bundle(missing_metric=("A", "expected_net_payoff")))
    assert _lookup(records, "A", "ECONOMIC_EDGE")["head_status"] == "BLOCKED"


def test_missing_metric_penalty_is_explicit():
    policy = scoring_policy(rules=(scoring_rule(missing_edge=MissingMetricAction.PENALIZE_HEAD, edge_missing_penalty=0.2),))
    records = _run(make_bundle(missing_metric=("A", "expected_net_payoff"), policy=policy))
    row = _lookup(records, "A", "ECONOMIC_EDGE")
    assert row["head_status"] == "PENALIZED"
    assert row["head_score"] == 0.2


def test_optional_metric_is_renormalized_not_defaulted():
    records = _run(make_bundle(missing_metric=("A", "convexity_quality")))
    row = _lookup(records, "A", "CONVEXITY_ASYMMETRY")
    assert row["head_status"] == "UNAVAILABLE"
    assert row["head_score"] is None


def test_other_group_change_does_not_affect_candidate():
    first = _run(make_bundle(separate_c_group=True))
    second = _run(make_bundle(separate_c_group=True, value_overrides={("C", "expected_net_payoff"): 1000.0}))
    assert _lookup(first, "A", "ECONOMIC_EDGE")["head_score"] == _lookup(second, "A", "ECONOMIC_EDGE")["head_score"]


def test_factor_adjusted_source_is_recorded():
    records = _run(make_bundle())
    stage = _lookup(records, "A", "ECONOMIC_EDGE")["stages"][0]
    assert stage["source_kind"] == "FACTOR_ADJUSTED"
