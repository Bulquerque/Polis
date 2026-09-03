from __future__ import annotations

from datetime import timedelta

from quant_pipeline.phase_09.subphases.s09_competition_promotion import (
    ChangeOrigin,
    LeaderboardPolicy,
    SubmissionRecord,
    assess_leaderboard_information_budget,
)

from tests.s09.conftest import H, NOW, public_reaction_submission


def policy() -> LeaderboardPolicy:
    return LeaderboardPolicy(
        policy_id="lb",
        maximum_submissions=5,
        information_budget=10.0,
        base_submission_cost=1.0,
        uncommitted_penalty=2.0,
        public_reaction_penalty=3.0,
        change_magnitude_weight=1.0,
        contamination_threshold=5.0,
        limited_use_threshold=3.0,
    )


def test_clean_empty_history() -> None:
    result, receipt = assess_leaderboard_information_budget(
        submission_ledger=(), policy=policy(), candidate_configuration_id="c"
    )
    assert result.output is not None
    assert result.output.state.value == "LEADERBOARD_CLEAN"
    assert receipt.eligible_for_submission


def test_public_score_reaction_contaminates(public_reaction_submission) -> None:
    parent = SubmissionRecord(
        submission_id="sub-1",
        configuration_id="c0",
        submitted_at=NOW - timedelta(hours=2),
        hypothesis_committed_at=NOW - timedelta(hours=3),
        hypothesis_text_hash=H,
        public_score=1.0,
    )
    result, receipt = assess_leaderboard_information_budget(
        submission_ledger=(parent, public_reaction_submission),
        policy=policy(),
        candidate_configuration_id="c1",
    )
    assert result.output is not None
    assert result.output.state.value == "LEADERBOARD_CONTAMINATED"
    assert not receipt.eligible_for_full_promotion
