from __future__ import annotations

from datetime import date, timedelta
from enum import StrEnum

import pytest

from quant_pipeline.phase_09.subphases.s09_competition_promotion import (
    CycleRef,
    FeedbackActivationLedgerEntry,
    FeedbackValidationState,
    assess_leaderboard_information_budget,
    build_competition_objective_policy,
    build_promotion_recommendation,
    build_robust_configuration_frontier,
    build_typed_feedback,
    qualify_champion_challengers,
    validate_feedback_for_future_activation,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import (
    ChallengerQualificationState,
    ChangeOrigin,
    ContaminationState,
    EvidenceQuality,
    FeedbackEffectType,
    FeedbackPhase,
    GateSeverity,
    GateState,
    LeaderboardState,
    ModuleStatus,
    OptimizationDirection,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion.hashing import (
    canonical_json_bytes,
    sha256_hex,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion import (
    m02_robust_configuration_frontier as m02,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion import (
    m05_promotion_recommendation as m05,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion.models import (
    ChallengerQualification,
    ChampionChallengerQualificationReport,
    FeedbackBuildPolicy,
    FeedbackEffectivenessRecord,
    LeaderboardPolicy,
    MetricValue,
    NumericChangeBounds,
    PairwiseComparisonEvidence,
    ParameterDimension,
    ParameterValue,
    PromotionGateReceipt,
    RootCauseEvidence,
    SubmissionChange,
    SubmissionRecord,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion.scoring import (
    configuration_utility,
    oriented,
    penalty_value,
)

from tests.s09.conftest import (
    H,
    NOW,
    artifact_ref,
    capabilities,
    card,
    configuration_cards,
    evidence,
    feedback_registry,
    gate_receipts,
    objective_spec,
    pairwise,
    parameter_space,
    promotion_source_context,
    root_causes,
)


def _objective():
    objective = build_competition_objective_policy(objective_spec()).output
    assert objective is not None
    return objective


def _frontier(cards=None):
    cards = configuration_cards() if cards is None else cards
    frontier = build_robust_configuration_frontier(
        objective=_objective(),
        configurations=cards,
        parameter_space=parameter_space(),
        model_confidence_set_ids=tuple(item.configuration_id for item in cards),
    ).output
    assert frontier is not None
    return frontier


def _leaderboard(state: LeaderboardState = LeaderboardState.LEADERBOARD_CLEAN):
    result, _ = assess_leaderboard_information_budget(
        submission_ledger=(),
        policy=LeaderboardPolicy(
            policy_id="lb",
            maximum_submissions=4,
            information_budget=10.0,
            base_submission_cost=1.0,
            uncommitted_penalty=2.0,
            public_reaction_penalty=3.0,
            change_magnitude_weight=1.0,
            contamination_threshold=7.0,
            limited_use_threshold=3.0,
        ),
        candidate_configuration_id="challenger-a",
    )
    assert result.output is not None
    return result.output.model_copy(
        update={
            "state": state,
            "full_promotion_eligible": state == LeaderboardState.LEADERBOARD_CLEAN,
        }
    )


def _qualification(state: ChallengerQualificationState):
    challenger = "challenger-a" if state.name.startswith("CHALLENGER_") else None
    qualifications = (
        (
            ChallengerQualification(
                challenger_configuration_id="challenger-a",
                state=state,
                effect_size=0.2,
                probability_of_superiority=0.96,
                contamination_state=ContaminationState.CLEAN,
            ),
        )
        if challenger is not None
        else ()
    )
    return ChampionChallengerQualificationReport(
        champion_configuration_id="champion",
        cohort_id="cohort-a",
        qualifications=qualifications,
        recommended_challenger_id=challenger,
        report_state=state,
    )


def test_hashing_and_scoring_edge_paths() -> None:
    class Example(StrEnum):
        VALUE = "value"

    assert canonical_json_bytes(date(2026, 8, 3)) == b'"2026-08-03"'
    assert canonical_json_bytes(Example.VALUE) == b'"value"'
    assert len(sha256_hex(objective_spec())) == 64
    with pytest.raises(TypeError):
        canonical_json_bytes(object())

    assert oriented(2.0, OptimizationDirection.MAXIMIZE) == 2.0
    assert oriented(2.0, OptimizationDirection.MINIMIZE) == -2.0
    rules = objective_spec().soft_penalties
    assert penalty_value(0.5, rules[0]) > 0.0
    maximize_rule = rules[0].model_copy(
        update={"direction": OptimizationDirection.MAXIMIZE, "reference_value": 1.0}
    )
    assert penalty_value(0.0, maximize_rule) > 0.0

    broken = card(
        "broken",
        score=1.0,
        lower=0.8,
        drawdown=0.1,
        cost=0.1,
        lookback=5,
        complexity=0.2,
    ).model_copy(update={"metrics": ()})
    with pytest.raises(KeyError):
        configuration_utility(broken, _objective())


def test_frontier_rejects_all_hard_gate_failure_modes() -> None:
    base = card(
        "base",
        score=1.0,
        lower=0.8,
        drawdown=0.1,
        cost=0.1,
        lookback=5,
        complexity=0.2,
    )
    variants = (
        base.model_copy(update={"gates": ()}),
        base.model_copy(update={"dsr": 0.1}),
        base.model_copy(update={"pbo": 0.9}),
        base.model_copy(update={"capacity_feasible": False}),
        base.model_copy(update={"stress_resilient": False}),
        base.model_copy(update={"live_degradation_detected": True}),
        base.model_copy(
            update={
                "metrics": tuple(
                    metric
                    for metric in base.metrics
                    if metric.metric_id != "competition_score_lower_bound"
                )
            }
        ),
    )
    result = build_robust_configuration_frontier(
        objective=_objective(),
        configurations=variants,
        parameter_space=parameter_space(),
        model_confidence_set_ids=("none",),
    )
    assert result.status == ModuleStatus.INSUFFICIENT_EVIDENCE
    assert result.output is not None
    assert result.output.state.value == "NO_ELIGIBLE_CONFIGURATION"
    assert result.output.warnings


def test_parameter_distance_validates_types_and_registry() -> None:
    numeric = ParameterDimension(name="x", numeric_minimum=0.0, numeric_maximum=10.0)
    categorical = ParameterDimension(name="kind", allowed_categories=("a", "b"))
    with pytest.raises(TypeError):
        m02._numeric_distance(True, 1, numeric)
    with pytest.raises(TypeError):
        m02._numeric_distance("1", 1, numeric)
    with pytest.raises(TypeError):
        m02._categorical_distance(1, "a", categorical)
    with pytest.raises(ValueError):
        m02._categorical_distance("z", "a", categorical)
    assert m02._categorical_distance("a", "a", categorical) == 0.0
    assert m02._categorical_distance("a", "b", categorical) == 1.0


def test_leaderboard_duplicate_incomplete_limited_and_exhausted_paths() -> None:
    policy = LeaderboardPolicy(
        policy_id="lb",
        maximum_submissions=2,
        information_budget=5.0,
        base_submission_cost=1.0,
        uncommitted_penalty=1.0,
        public_reaction_penalty=2.0,
        change_magnitude_weight=1.0,
        contamination_threshold=4.0,
        limited_use_threshold=2.0,
    )
    first = SubmissionRecord(
        submission_id="s1",
        configuration_id="c1",
        submitted_at=NOW - timedelta(hours=4),
        hypothesis_committed_at=NOW - timedelta(hours=5),
        hypothesis_text_hash=H,
        public_score=1.0,
    )
    duplicate = first.model_copy(update={"configuration_id": "c2"})
    result, receipt = assess_leaderboard_information_budget(
        submission_ledger=(first, duplicate),
        policy=policy,
        candidate_configuration_id="c3",
    )
    assert result.status == ModuleStatus.INVALID
    assert not receipt.eligible_for_submission

    incomplete = SubmissionRecord(
        submission_id="s2",
        configuration_id="c2",
        submitted_at=NOW - timedelta(hours=2),
        hypothesis_committed_at=None,
        hypothesis_text_hash=None,
        public_score=1.1,
        parent_submission_id="missing",
        changes_after_parent=(
            SubmissionChange(
                parameter_name="lookback",
                normalized_magnitude=0.5,
                origin=ChangeOrigin.UNKNOWN,
                rationale="unclassified search change",
            ),
        ),
    )
    result, receipt = assess_leaderboard_information_budget(
        submission_ledger=(first, incomplete),
        policy=policy,
        candidate_configuration_id="c3",
    )
    assert result.status == ModuleStatus.INVALID
    assert result.output is not None
    assert result.output.state == LeaderboardState.SUBMISSION_HISTORY_INCOMPLETE
    assert not receipt.eligible_for_submission

    second = incomplete.model_copy(update={"parent_submission_id": "s1"})
    result, receipt = assess_leaderboard_information_budget(
        submission_ledger=(first, second),
        policy=policy,
        candidate_configuration_id="c3",
    )
    assert result.output is not None
    assert result.output.state == LeaderboardState.SUBMISSION_BUDGET_EXHAUSTED
    assert not receipt.eligible_for_full_promotion


def test_qualification_covers_invalid_missing_quarantine_and_limited_paths() -> None:
    objective = _objective()
    base_cards = configuration_cards()
    frontier = _frontier(base_cards)

    wrong_cohort = base_cards[1].model_copy(update={"cohort_id": "other"})
    cards = (base_cards[0], wrong_cohort)
    result = qualify_champion_challengers(
        objective=objective,
        frontier=frontier,
        leaderboard=_leaderboard(),
        configurations=cards,
        champion_configuration_id="champion",
        challenger_configuration_ids=("challenger-a",),
        pairwise_evidence=(),
    )
    assert result.status == ModuleStatus.INVALID

    result = qualify_champion_challengers(
        objective=objective,
        frontier=frontier,
        leaderboard=_leaderboard(),
        configurations=base_cards,
        champion_configuration_id="champion",
        challenger_configuration_ids=("challenger-a",),
        pairwise_evidence=(),
    )
    assert result.status == ModuleStatus.INSUFFICIENT_EVIDENCE

    degraded = base_cards[1].model_copy(update={"live_degradation_detected": True})
    result = qualify_champion_challengers(
        objective=objective,
        frontier=frontier,
        leaderboard=_leaderboard(),
        configurations=(base_cards[0], degraded),
        champion_configuration_id="champion",
        challenger_configuration_ids=("challenger-a",),
        pairwise_evidence=(pairwise()[0],),
    )
    assert result.output is not None
    assert result.output.report_state == ChallengerQualificationState.QUARANTINE_CHALLENGER

    low_effect = pairwise()[0].model_copy(
        update={"effect_size": 0.01, "effect_lower_bound": 0.0, "effect_upper_bound": 0.02}
    )
    result = qualify_champion_challengers(
        objective=objective,
        frontier=frontier,
        leaderboard=_leaderboard(),
        configurations=base_cards,
        champion_configuration_id="champion",
        challenger_configuration_ids=("challenger-a",),
        pairwise_evidence=(low_effect,),
    )
    assert result.output is not None
    assert result.output.report_state == (
        ChallengerQualificationState.STATISTICALLY_INDISTINGUISHABLE
    )

    result = qualify_champion_challengers(
        objective=objective,
        frontier=frontier,
        leaderboard=_leaderboard(LeaderboardState.LEADERBOARD_CONTAMINATED),
        configurations=base_cards,
        champion_configuration_id="champion",
        challenger_configuration_ids=("challenger-a",),
        pairwise_evidence=(pairwise()[0],),
    )
    assert result.output is not None
    assert result.output.report_state == ChallengerQualificationState.CHALLENGER_SHADOW_ONLY

    result = qualify_champion_challengers(
        objective=objective,
        frontier=frontier,
        leaderboard=_leaderboard(LeaderboardState.LEADERBOARD_LIMITED_USE),
        configurations=base_cards,
        champion_configuration_id="champion",
        challenger_configuration_ids=("challenger-a",),
        pairwise_evidence=(pairwise()[0],),
    )
    assert result.output is not None
    assert result.output.report_state == (
        ChallengerQualificationState.CHALLENGER_QUALIFIED_LIMITED_CAPITAL
    )


def test_promotion_mapping_and_critical_failure_paths() -> None:
    expected_states = {
        ChallengerQualificationState.CHALLENGER_QUALIFIED,
        ChallengerQualificationState.CHALLENGER_QUALIFIED_LIMITED_CAPITAL,
        ChallengerQualificationState.CHALLENGER_SHADOW_ONLY,
        ChallengerQualificationState.RETAIN_CHAMPION,
        ChallengerQualificationState.STATISTICALLY_INDISTINGUISHABLE,
        ChallengerQualificationState.QUARANTINE_CHALLENGER,
        ChallengerQualificationState.INSUFFICIENT_EVIDENCE,
        ChallengerQualificationState.COMPARISON_INVALID,
    }
    assert {m05._map_qualification_state(state) for state in expected_states}

    from quant_pipeline.phase_09.subphases.s09_competition_promotion.models import build_promotion_gate_receipt
    failed = build_promotion_gate_receipt(
        gate_id="statistical", run_id="run-1", cycle=artifact_ref().cycle,
        subject_configuration_ids=("challenger-a", "challenger-b", "challenger-c"), source_bundle_sha256=artifact_ref().payload_sha256,
        producer_module_id="P9.S9.GATE.STATISTICAL", state=GateState.FAIL,
        severity=GateSeverity.CRITICAL, evidence_refs=(evidence("failed-gate"),),
        reason_codes=("P9_PROMOTION_CRITICAL_GATE_FAILED",), limitations=(),
    )
    result = build_promotion_recommendation(
        objective=_objective(),
        qualification=_qualification(ChallengerQualificationState.CHALLENGER_QUALIFIED),
        gate_receipts=(gate_receipts()[0], failed),
        source_context=promotion_source_context(cards=configuration_cards(), ref=artifact_ref()),
        created_at=NOW,
    )
    assert result.output is not None
    assert result.output.recommendation.recommendation_state.value == "QUARANTINE_RECOMMENDED"

    shadow = build_promotion_recommendation(
        objective=_objective(),
        qualification=_qualification(ChallengerQualificationState.CHALLENGER_SHADOW_ONLY),
        gate_receipts=gate_receipts(),
        source_context=promotion_source_context(cards=configuration_cards(), ref=artifact_ref()),
        created_at=NOW,
    )
    assert shadow.output is not None
    assert shadow.output.evidence_bundle.rollback_requirements


def test_feedback_builder_rejects_registry_confidence_materiality_regression_and_bounds() -> None:
    base = root_causes()[0]
    cases = (
        base.model_copy(update={"target_policy_id": "missing"}),
        base.model_copy(update={"feedback_type": "not-allowed"}),
        base.model_copy(update={"confidence": 0.1}),
        base.model_copy(update={"economic_materiality": 0.0}),
        base.model_copy(
            update={
                "numeric_change_bounds": (
                    NumericChangeBounds(
                        parameter_name="cost_buffer",
                        minimum=0.0,
                        maximum=1.0,
                        maximum_absolute_delta=0.9,
                    ),
                )
            }
        ),
    )
    previous = (
        FeedbackEffectivenessRecord(
            target_phase=base.target_phase,
            target_policy_id=base.target_policy_id,
            effectiveness_score=-0.5,
            regressive=True,
        ),
    )
    result = build_typed_feedback(
        root_causes=cases,
        registry=feedback_registry(),
        previous_effectiveness=previous,
        source_cycle=CycleRef(cycle_id="cycle-5", ordinal=5),
        target_cycle=CycleRef(cycle_id="cycle-6", ordinal=6),
        policy=FeedbackBuildPolicy(minimum_economic_materiality=0.5),
    )
    assert result.output is not None
    assert not result.output.feedback_packages
    assert len(result.output.rejected_root_cause_ids) == len(cases)


def test_feedback_activation_rejection_and_reservation_states() -> None:
    built = build_typed_feedback(
        root_causes=root_causes(),
        registry=feedback_registry(),
        previous_effectiveness=(),
        source_cycle=CycleRef(cycle_id="cycle-5", ordinal=5),
        target_cycle=CycleRef(cycle_id="cycle-6", ordinal=6),
    ).output
    assert built is not None
    packages = built.feedback_packages

    unavailable = tuple(
        capability.model_copy(update={"available": False}) for capability in capabilities()
    )
    reserved = validate_feedback_for_future_activation(
        candidate_manifest=built,
        registry=feedback_registry(),
        target_capabilities=unavailable,
        previous_activation_ledger=(),
        current_cycle=CycleRef(cycle_id="cycle-5", ordinal=5),
    )
    assert reserved.output is not None
    assert reserved.output.reserved_count == len(packages)

    invalid_version = packages[0].model_copy(update={"target_policy_version": "bad"})
    invalid_manifest = built.model_copy(update={"feedback_packages": (invalid_version,)})
    with pytest.raises(ValueError):
        validate_feedback_for_future_activation(
            candidate_manifest=invalid_manifest,
            registry=feedback_registry(),
            target_capabilities=capabilities(),
            previous_activation_ledger=(),
            current_cycle=CycleRef(cycle_id="cycle-5", ordinal=5),
        )

    ledger = (
        FeedbackActivationLedgerEntry(
            feedback_id=packages[0].feedback_id,
            state=FeedbackValidationState.VALIDATED_PENDING_P0,
            target_cycle=packages[0].target_cycle,
        ),
    )
    duplicate = validate_feedback_for_future_activation(
        candidate_manifest=built,
        registry=feedback_registry(),
        target_capabilities=capabilities(),
        previous_activation_ledger=ledger,
        current_cycle=CycleRef(cycle_id="cycle-5", ordinal=5),
    )
    assert duplicate.output is not None
    assert duplicate.output.rejected_count >= 1
