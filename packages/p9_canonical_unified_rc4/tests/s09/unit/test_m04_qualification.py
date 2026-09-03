from __future__ import annotations

from quant_pipeline.phase_09.subphases.s09_competition_promotion import (
    assess_leaderboard_information_budget,
    build_competition_objective_policy,
    build_robust_configuration_frontier,
    qualify_champion_challengers,
)

from tests.s09.conftest import configuration_cards, objective_spec, pairwise, parameter_space


def test_qualifies_robust_challenger(valid_input_bundle) -> None:
    objective = build_competition_objective_policy(objective_spec()).output
    assert objective is not None
    cards = configuration_cards()
    frontier = build_robust_configuration_frontier(
        objective=objective,
        configurations=cards,
        parameter_space=parameter_space(),
        model_confidence_set_ids=tuple(card.configuration_id for card in cards),
    ).output
    assert frontier is not None
    leaderboard = assess_leaderboard_information_budget(
        submission_ledger=(),
        policy=valid_input_bundle.leaderboard_policy,
        candidate_configuration_id="challenger-a",
    )[0].output
    assert leaderboard is not None
    result = qualify_champion_challengers(
        objective=objective,
        frontier=frontier,
        leaderboard=leaderboard,
        configurations=cards,
        champion_configuration_id="champion",
        challenger_configuration_ids=("challenger-a", "challenger-b", "challenger-c"),
        pairwise_evidence=pairwise(),
    )
    assert result.output is not None
    assert result.output.recommended_challenger_id is not None
    assert result.output.report_state.value.startswith("CHALLENGER_")
