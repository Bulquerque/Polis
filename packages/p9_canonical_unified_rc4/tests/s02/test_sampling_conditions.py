from __future__ import annotations

import json
import random

import pytest

from quant_pipeline.phase_09.subphases.s02_experiment_governance.conditions import (
    condition_matches,
    parameter_is_active,
    topological_parameter_order,
)
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.base import (
    ConditionOperator,
    ParameterKind,
    ParameterScale,
)
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.search_space import (
    ActivationCondition,
    CompiledParameterDomain,
    SearchSpaceConstraintEdge,
)
from quant_pipeline.phase_09.subphases.s02_experiment_governance.sampling import (
    boundary_parameter_ids,
    finite_domain_values,
    iter_grid_assignments,
    sample_random_assignment,
    take_unique_random_assignments,
)


def condition(operator, values=("A",)):
    return ActivationCondition(
        parent_parameter_id="P8.optimizer.type",
        operator=operator,
        values=values,
    )


def test_all_condition_operators() -> None:
    values = {"P8.optimizer.type": "A"}
    assert condition_matches(condition(ConditionOperator.EQUALS), values)
    assert not condition_matches(condition(ConditionOperator.NOT_EQUALS), values)
    assert condition_matches(condition(ConditionOperator.IN, ("A", "B")), values)
    assert not condition_matches(condition(ConditionOperator.NOT_IN, ("A", "B")), values)
    assert not condition_matches(condition(ConditionOperator.EQUALS), {})
    assert parameter_is_active((condition(ConditionOperator.EQUALS),), values)


def test_topological_order_rejects_unknown_and_cycle() -> None:
    with pytest.raises(ValueError, match="unknown"):
        topological_parameter_order(
            ("P5.a.x",),
            (SearchSpaceConstraintEdge(parent_parameter_id="P5.a.x", child_parameter_id="P6.b.x"),),
        )
    edges = (
        SearchSpaceConstraintEdge(parent_parameter_id="P5.a.x", child_parameter_id="P6.b.x"),
        SearchSpaceConstraintEdge(parent_parameter_id="P6.b.x", child_parameter_id="P5.a.x"),
    )
    with pytest.raises(ValueError, match="cycle"):
        topological_parameter_order(("P5.a.x", "P6.b.x"), edges)


def domain(**updates):
    raw = {
        "parameter_id": "P5.alpha.value",
        "kind": "FLOAT",
        "scale": "LINEAR",
        "discrete_values": [],
        "lower": 1.0,
        "upper": 9.0,
        "grid_points": 3,
        "active_when": [],
        "topological_index": 0,
    }
    raw.update(updates)
    return CompiledParameterDomain.model_validate_json(json.dumps(raw))


def test_finite_domain_linear_log_integer_and_discrete() -> None:
    assert finite_domain_values(domain()) == (1.0, 5.0, 9.0)
    log_values = finite_domain_values(domain(scale="LOG", lower=1.0, upper=100.0))
    assert log_values[0] == pytest.approx(1.0)
    assert log_values[-1] == pytest.approx(100.0)
    ints = finite_domain_values(domain(kind="INTEGER", lower=1, upper=5, grid_points=3))
    assert ints == (1, 3, 5)
    discrete = domain(discrete_values=["A", "B"], lower=None, upper=None, grid_points=None, kind="CATEGORICAL")
    assert finite_domain_values(discrete) == ("A", "B")


def test_integer_grid_collapse_is_rejected() -> None:
    with pytest.raises(ValueError, match="collapsed"):
        finite_domain_values(domain(kind="INTEGER", lower=1, upper=1.1, grid_points=3))


def test_grid_and_random_sampling_are_deterministic(result) -> None:
    space = result.s2_outputs.compiled_search_space
    grid = list(iter_grid_assignments(space))
    assert len(grid) == 189
    assert sample_random_assignment(space, random.Random(9)) == sample_random_assignment(space, random.Random(9))
    first = take_unique_random_assignments(space, count=10, seed=3)
    second = take_unique_random_assignments(space, count=10, seed=3)
    assert first == second
    assert len(first) == 10


def test_boundary_detection(result) -> None:
    space = result.s2_outputs.compiled_search_space
    assignment = {
        "P5.ensemble.member_weight": 0.2,
        "P6.solver.complexity_penalty": 0.5,
    }
    boundaries = boundary_parameter_ids(assignment, space.parameters)
    assert "P5.ensemble.member_weight" in boundaries
    assert "P6.solver.complexity_penalty" not in boundaries
