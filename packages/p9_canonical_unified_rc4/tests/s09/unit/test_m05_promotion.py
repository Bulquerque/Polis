from __future__ import annotations

from quant_pipeline.phase_09.subphases.s09_competition_promotion import (
    ChampionChallengerQualificationReport,
    ChallengerQualificationState,
    build_competition_objective_policy,
    build_promotion_recommendation,
)

from tests.s09.conftest import NOW, artifact_ref, configuration_cards, gate_receipts, objective_spec, promotion_source_context


def qualification() -> ChampionChallengerQualificationReport:
    return ChampionChallengerQualificationReport(
        champion_configuration_id="champion",
        cohort_id="cohort-a",
        qualifications=(),
        recommended_challenger_id=None,
        report_state=ChallengerQualificationState.RETAIN_CHAMPION,
    )


def test_p9_only_requests_p0_authorization() -> None:
    objective = build_competition_objective_policy(objective_spec()).output
    assert objective is not None
    result = build_promotion_recommendation(
        objective=objective,
        qualification=qualification(),
        gate_receipts=gate_receipts(),
        source_context=promotion_source_context(cards=configuration_cards(), ref=artifact_ref()),
        created_at=NOW,
    )
    assert result.output is not None
    assert result.output.p0_authorization_request.authorization_state.value == "PENDING_P0"
    assert result.output.recommendation.authorization_required


def test_missing_gate_becomes_insufficient_evidence() -> None:
    objective = build_competition_objective_policy(objective_spec()).output
    assert objective is not None
    result = build_promotion_recommendation(
        objective=objective,
        qualification=qualification(),
        gate_receipts=gate_receipts()[:1],
        source_context=promotion_source_context(cards=configuration_cards(), ref=artifact_ref()),
        created_at=NOW,
    )
    assert result.output is not None
    assert result.output.recommendation.recommendation_state.value == "INSUFFICIENT_EVIDENCE"
