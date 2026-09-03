from __future__ import annotations

import random

from quant_pipeline.phase_09.subphases.s02_experiment_governance.conditions import topological_parameter_order
from quant_pipeline.phase_09.subphases.s02_experiment_governance.sampling import assignment_key


def test_assignment_key_is_order_invariant() -> None:
    items = [("P5.x.a", 1), ("P6.y.b", 2), ("P7.z.c", True)]
    expected = assignment_key(dict(items))
    for seed in range(20):
        shuffled = items[:]
        random.Random(seed).shuffle(shuffled)
        assert assignment_key(dict(shuffled)) == expected


def test_topological_order_is_stable_without_edges() -> None:
    ids = ("P8.z.x", "P5.a.x", "P7.y.x")
    assert topological_parameter_order(ids, ()) == tuple(sorted(ids))
