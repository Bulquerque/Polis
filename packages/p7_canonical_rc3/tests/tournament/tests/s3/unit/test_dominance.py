from __future__ import annotations

import pytest

from quant_pipeline.phase_07_strategy_tournament.tournament.domain.errors import ResourceBudgetExceeded
from quant_pipeline.phase_07_strategy_tournament.tournament.s3_runner import run_subphase

from tests.tournament.tests.s3.factories import execution_config, make_bundle


def test_known_strict_dominance_relation():
    result = run_subphase(make_bundle(), execution_config())
    relations = result["outputs"]["dominance_relation_panel"]["records"]
    assert [(row["dominator_candidate_id"], row["dominated_candidate_id"]) for row in relations] == [("A", "B")]
    assert all(any(item["materially_better"] for item in row["evidence"]) for row in relations)


def test_cross_group_candidates_are_never_compared():
    result = run_subphase(make_bundle(separate_groups=True), execution_config())
    relations = result["outputs"]["dominance_relation_panel"]["records"]
    assert not any({row["dominator_candidate_id"], row["dominated_candidate_id"]} == {"A", "B"} for row in relations)


def test_missing_required_metric_is_incomparable_not_dominated():
    result = run_subphase(make_bundle(missing_metric=("B", "expected_shortfall")), execution_config())
    survivors = result["outputs"]["dominance_survivor_panel"]["records"]
    row = next(row for row in survivors if row["candidate_id"] == "B")
    assert row["status"] == "INCOMPARABLE_MISSING_REQUIRED"
    assert row["eligible_for_pareto"] is False
    frontier = next(row for row in result["outputs"]["pareto_frontier_panel"]["records"] if row["candidate_id"] == "B")
    assert frontier["frontier_status"] == "INCOMPARABLE"
    assert frontier["frontier_layer"] is None


def test_candidate_identity_is_conserved():
    result = run_subphase(make_bundle(), execution_config())
    dominated = {row["candidate_id"] for row in result["outputs"]["dominated_candidate_panel"]["records"]}
    survivors = {row["candidate_id"] for row in result["outputs"]["dominance_survivor_panel"]["records"]}
    assert dominated.isdisjoint(survivors)
    assert dominated | survivors == {"A", "B", "C"}


def test_group_budget_fails_before_unbounded_pairwise_work():
    with pytest.raises(ResourceBudgetExceeded) as exc_info:
        run_subphase(make_bundle(max_group_size=2), execution_config())
    assert exc_info.value.code == "P7_S3_EXACT_GROUP_BUDGET_EXCEEDED"
