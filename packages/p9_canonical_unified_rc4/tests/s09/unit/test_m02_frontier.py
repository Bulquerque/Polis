from __future__ import annotations

from quant_pipeline.phase_09.subphases.s09_competition_promotion import (
    FrontierBuildPolicy,
    build_competition_objective_policy,
    build_robust_configuration_frontier,
)

from tests.s09.conftest import configuration_cards, objective_spec, parameter_space


def test_builds_frontier_and_plateau() -> None:
    objective = build_competition_objective_policy(objective_spec()).output
    assert objective is not None
    cards = configuration_cards()
    result = build_robust_configuration_frontier(
        objective=objective,
        configurations=cards,
        parameter_space=parameter_space(),
        model_confidence_set_ids=tuple(card.configuration_id for card in cards),
        build_policy=FrontierBuildPolicy(
            neighbor_radius=0.2,
            minimum_region_size=3,
            maximum_utility_dispersion=0.1,
        ),
    )
    assert result.output is not None
    cohort = result.output.cohorts[0]
    assert "challenger-c" in cohort.frontier_configuration_ids
    assert any(region.state.value == "ROBUST_PLATEAU" for region in cohort.robust_regions)


def test_frontier_is_permutation_invariant() -> None:
    objective = build_competition_objective_policy(objective_spec()).output
    assert objective is not None
    cards = configuration_cards()
    kwargs = dict(
        objective=objective,
        parameter_space=parameter_space(),
        model_confidence_set_ids=tuple(card.configuration_id for card in cards),
    )
    first = build_robust_configuration_frontier(configurations=cards, **kwargs)
    second = build_robust_configuration_frontier(configurations=tuple(reversed(cards)), **kwargs)
    assert first.output_sha256 == second.output_sha256
