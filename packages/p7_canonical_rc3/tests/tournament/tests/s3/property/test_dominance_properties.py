from __future__ import annotations

import random

from quant_pipeline.phase_07_strategy_tournament.tournament.boundary.records import MetricPolicy
from quant_pipeline.phase_07_strategy_tournament.tournament.domain.enums import Direction, MissingAction
from quant_pipeline.phase_07_strategy_tournament.tournament.subphases.s3.dominance import _dominates


def _policies():
    return {
        metric_id: MetricPolicy(
            metric_id=metric_id,
            canonical_units="unit",
            direction=Direction.MAXIMIZE,
            semantic_version="1.0.0",
            missing_action=MissingAction.BLOCK,
            active_for_dominance=True,
            epsilon_absolute=1e-12,
        )
        for metric_id in ("x", "y", "z")
    }


def test_strict_dominance_is_irreflexive_and_antisymmetric_on_random_vectors():
    rng = random.Random(8128)
    policies = _policies()
    active = tuple(policies)
    for _ in range(500):
        first = {metric_id: rng.uniform(-10, 10) for metric_id in active}
        second = {metric_id: rng.uniform(-10, 10) for metric_id in active}
        first_wins, _ = _dominates(first, second, policies, active)
        second_wins, _ = _dominates(second, first, policies, active)
        self_wins, _ = _dominates(first, first, policies, active)
        assert not self_wins
        assert not (first_wins and second_wins)


def test_material_improvement_in_all_metrics_dominates():
    policies = _policies()
    active = tuple(policies)
    first = {metric_id: 2.0 for metric_id in active}
    second = {metric_id: 1.0 for metric_id in active}
    wins, evidence = _dominates(first, second, policies, active)
    assert wins
    assert all(row.materially_better for row in evidence)
