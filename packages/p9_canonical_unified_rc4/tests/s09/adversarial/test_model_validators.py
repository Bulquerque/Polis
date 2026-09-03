from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s09_competition_promotion import (
    ChampionChallengerQualificationReport,
    ChallengerQualificationState,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import (
    ChangeOrigin,
    ContaminationState,
    FeedbackBuildState,
    FeedbackEffectType,
    FeedbackPhase,
    FeedbackValidationState,
    GateSeverity,
    GateState,
    ModuleStatus,
    P0AuthorizationState,
    RecommendationState,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion.hashing import sha256_hex
from quant_pipeline.phase_09.subphases.s09_competition_promotion.models import (
    CategoricalChangeBounds,
    ChallengerQualification,
    CompetitionObjectiveSpec,
    ConfigurationEvaluationCard,
    CycleRef,
    FeedbackActivationLedgerEntry,
    FeedbackCandidateManifest,
    FeedbackCandidateManifest,
    FeedbackPolicyRegistry,
    FeedbackValidationDecision,
    FrontierAxis,
    GateEvidence,
    HardGateRule,
    LeaderboardPolicy,
    MetricValue,
    ModuleDiagnostics,
    ModuleResult,
    NumericChangeBounds,
    P0PromotionAuthorizationRequest,
    PairwiseComparisonEvidence,
    ParameterDimension,
    ParameterSpaceRegistry,
    PromotionEvidenceBundle,
    PromotionEvidenceInputBundle,
    PromotionGateReceipt,
    build_promotion_gate_receipt,
    PromotionRecommendation,
    RobustConfigurationFrontier,
    S9ExecutionEnvelope,
    SoftPenaltyRule,
    SubmissionChange,
    SubmissionRecord,
    TieBreakerRule,
    ValidatedNextCycleFeedbackManifest,
)

from tests.s09.conftest import (
    H,
    NOW,
    artifact_ref,
    card,
    configuration_cards,
    evidence,
    feedback_registry,
    objective_spec,
    parameter_space,
)


def _invalid(model, **updates):
    payload = model.model_dump(mode="python")
    payload.update(updates)
    with pytest.raises(ValidationError):
        type(model).model_validate(payload)


def test_policy_and_parameter_model_validators() -> None:
    with pytest.raises(ValidationError):
        HardGateRule(gate_id="g", accepted_states=())
    with pytest.raises(ValidationError):
        HardGateRule(gate_id="g", accepted_states=("PASS", "PASS"))

    spec = objective_spec()
    _invalid(spec, committed_at=spec.evaluation_started_at)
    _invalid(spec, primary_score_version="2.0.0")
    _invalid(spec, hard_gates=())
    _invalid(spec, frontier_axes=())
    _invalid(spec, hard_gates=(spec.hard_gates[0], spec.hard_gates[0]))
    _invalid(spec, soft_penalties=(spec.soft_penalties[0], spec.soft_penalties[0]))
    _invalid(spec, tie_breakers=(spec.tie_breakers[0], spec.tie_breakers[0]))
    _invalid(spec, frontier_axes=(spec.frontier_axes[0], spec.frontier_axes[0]))
    _invalid(spec, allowed_deployment_stages=())

    with pytest.raises(ValidationError):
        ParameterDimension(name="x")
    with pytest.raises(ValidationError):
        ParameterDimension(
            name="x",
            numeric_minimum=1.0,
            numeric_maximum=1.0,
        )
    with pytest.raises(ValidationError):
        ParameterDimension(name="x", allowed_categories=("a", "a"))
    with pytest.raises(ValidationError):
        ParameterSpaceRegistry(
            schema_version="1.0.0",
            dimensions=(parameter_space().dimensions[0], parameter_space().dimensions[0]),
        )


def test_configuration_metric_and_frontier_validators() -> None:
    with pytest.raises(ValidationError):
        MetricValue(metric_id="x", value=float("nan"), unit="score")

    base = configuration_cards()[0]
    _invalid(base, parameters=(base.parameters[0], base.parameters[0]))
    _invalid(base, metrics=(base.metrics[0], base.metrics[0]))
    _invalid(base, gates=(base.gates[0], base.gates[0]))

    cohort = build_empty_frontier().cohorts[0]
    with pytest.raises(ValidationError):
        RobustConfigurationFrontier(
            state=build_empty_frontier().state,
            cohorts=(cohort, cohort),
        )


def build_empty_frontier() -> RobustConfigurationFrontier:
    from quant_pipeline.phase_09.subphases.s09_competition_promotion.models import (
        CohortFrontier,
    )
    from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import FrontierState

    cohort = CohortFrontier(
        cohort_id="c",
        frontier_configuration_ids=(),
        eligible_configuration_ids=(),
        ineligible_configuration_ids=(),
        robust_regions=(),
        dominated=(),
    )
    return RobustConfigurationFrontier(
        state=FrontierState.NO_ELIGIBLE_CONFIGURATION,
        cohorts=(cohort,),
    )


def test_leaderboard_and_pairwise_validators() -> None:
    change = SubmissionChange(
        parameter_name="x",
        normalized_magnitude=0.1,
        origin=ChangeOrigin.PRECOMMITTED,
        rationale="planned",
    )
    with pytest.raises(ValidationError):
        SubmissionRecord(
            submission_id="s",
            configuration_id="c",
            submitted_at=NOW,
            hypothesis_committed_at=NOW - timedelta(hours=1),
            hypothesis_text_hash=None,
            public_score=1.0,
        )
    with pytest.raises(ValidationError):
        SubmissionRecord(
            submission_id="s",
            configuration_id="c",
            submitted_at=NOW,
            hypothesis_committed_at=NOW,
            hypothesis_text_hash=H,
            public_score=1.0,
        )
    with pytest.raises(ValidationError):
        SubmissionRecord(
            submission_id="s",
            configuration_id="c",
            submitted_at=NOW,
            hypothesis_committed_at=None,
            hypothesis_text_hash=None,
            public_score=1.0,
            changes_after_parent=(change,),
        )
    with pytest.raises(ValidationError):
        SubmissionRecord(
            submission_id="s",
            configuration_id="c",
            submitted_at=NOW,
            hypothesis_committed_at=None,
            hypothesis_text_hash=None,
            public_score=float("inf"),
        )
    with pytest.raises(ValidationError):
        LeaderboardPolicy(
            policy_id="p",
            maximum_submissions=1,
            information_budget=5.0,
            base_submission_cost=1.0,
            uncommitted_penalty=0.0,
            public_reaction_penalty=0.0,
            change_magnitude_weight=0.0,
            contamination_threshold=4.0,
            limited_use_threshold=4.0,
        )
    with pytest.raises(ValidationError):
        LeaderboardPolicy(
            policy_id="p",
            maximum_submissions=1,
            information_budget=3.0,
            base_submission_cost=1.0,
            uncommitted_penalty=0.0,
            public_reaction_penalty=0.0,
            change_magnitude_weight=0.0,
            contamination_threshold=4.0,
            limited_use_threshold=2.0,
        )

    base = PairwiseComparisonEvidence(
        champion_configuration_id="a",
        challenger_configuration_id="b",
        cohort_id="c",
        effect_size=0.2,
        effect_lower_bound=0.1,
        effect_upper_bound=0.3,
        probability_of_superiority=0.9,
        paired_bootstrap_available=True,
    )
    _invalid(base, effect_lower_bound=0.4)
    _invalid(base, effect_size=0.5)
    _invalid(base, live_effect_size=0.1)


def test_common_result_and_gate_validators() -> None:
    with pytest.raises(ValidationError):
        GateEvidence(
            gate_id="g",
            state=GateState.FAIL,
            severity=GateSeverity.BLOCKING,
        )

    diagnostics = ModuleDiagnostics()
    with pytest.raises(ValidationError):
        ModuleResult[str](
            module_id="P9.S9.M01",
            status=ModuleStatus.SUCCESS,
            output=None,
            diagnostics=diagnostics,
        )
    with pytest.raises(ValidationError):
        ModuleResult[str](
            module_id="P9.S9.M01",
            status=ModuleStatus.LIMITED,
            output=None,
            diagnostics=diagnostics,
            output_sha256=H,
        )
    with pytest.raises(ValidationError):
        ModuleResult[str](
            module_id="P9.S9.M01",
            status=ModuleStatus.SUCCESS,
            output="value",
            diagnostics=diagnostics,
            output_sha256=H,
        )
    with pytest.raises(ValidationError):
        ModuleResult[str](
            module_id="P9.S9.M01",
            status=ModuleStatus.INVALID,
            output=None,
            diagnostics=diagnostics,
        )
    valid_hash = sha256_hex("value")
    result = ModuleResult[str](
        module_id="P9.S9.M01",
        status=ModuleStatus.SUCCESS,
        output="value",
        diagnostics=diagnostics,
        output_sha256=valid_hash,
    )
    assert result.output == "value"


def test_feedback_and_promotion_model_validators() -> None:
    with pytest.raises(ValidationError):
        NumericChangeBounds(parameter_name="x")
    with pytest.raises(ValidationError):
        NumericChangeBounds(parameter_name="x", minimum=2.0, maximum=1.0)
    with pytest.raises(ValidationError):
        CategoricalChangeBounds(parameter_name="x", allowed_values=())
    with pytest.raises(ValidationError):
        CategoricalChangeBounds(parameter_name="x", allowed_values=("a", "a"))

    target = feedback_registry().targets[0]
    with pytest.raises(ValidationError):
        FeedbackPolicyRegistry(
            registry_version="1.0.0",
            targets=(target, target),
        )

    with pytest.raises(ValidationError):
        build_promotion_gate_receipt(
            gate_id="g", run_id="run-1", cycle=artifact_ref().cycle,
            subject_configuration_ids=("challenger-a", "challenger-b", "challenger-c"), source_bundle_sha256=artifact_ref().payload_sha256,
            producer_module_id="P9.S9.GATE.TEST", state=GateState.FAIL,
            severity=GateSeverity.CRITICAL, evidence_refs=(), reason_codes=(), limitations=(),
        )
    gate = build_promotion_gate_receipt(
        gate_id="g", run_id="run-1", cycle=artifact_ref().cycle,
        subject_configuration_ids=("challenger-a", "challenger-b", "challenger-c"), source_bundle_sha256=artifact_ref().payload_sha256,
        producer_module_id="P9.S9.GATE.TEST", state=GateState.PASS,
        severity=GateSeverity.BLOCKING, evidence_refs=(), reason_codes=(), limitations=(),
    )
    with pytest.raises(ValidationError):
        PromotionEvidenceBundle(
            recommendation_candidate_id=None,
            gate_receipts=(gate, gate),
        )

    evidence_bundle = PromotionEvidenceBundle(
        recommendation_candidate_id=None,
        gate_receipts=(gate,),
    )
    with pytest.raises(ValidationError):
        PromotionRecommendation(
            recommendation_id="r",
            recommendation_state=RecommendationState.RETAIN_CHAMPION,
            champion_configuration_id="champion",
            challenger_configuration_id=None,
            requested_deployment_stage="RETAIN_CURRENT",
            evidence_bundle=evidence_bundle,
            reason_codes=("P9_PROMOTION_RECOMMENDATION_COMPILED",),
            created_at=NOW,
            authorization_required=False,
        )
    with pytest.raises(ValidationError):
        PromotionRecommendation(
            recommendation_id="r",
            recommendation_state=RecommendationState.PROMOTE_RECOMMENDED,
            champion_configuration_id="champion",
            challenger_configuration_id=None,
            requested_deployment_stage="FULL_PRODUCTION",
            evidence_bundle=evidence_bundle,
            reason_codes=("P9_PROMOTION_RECOMMENDATION_COMPILED",),
            created_at=NOW,
        )
    invalid_request = P0PromotionAuthorizationRequest.model_construct(
        request_id="p0",
        recommendation_id="r",
        recommendation_state=RecommendationState.RETAIN_CHAMPION,
        requested_deployment_stage="RETAIN_CURRENT",
        authorization_state="AUTHORIZED",
        submitted_at=NOW,
        evidence_bundle_sha256=H,
    )
    with pytest.raises(ValueError):
        invalid_request.preserve_p0_authority()


def test_feedback_manifest_partition_and_bundle_identity_validators(
    valid_input_bundle: PromotionEvidenceInputBundle,
) -> None:
    package = valid_feedback_package()
    with pytest.raises(ValidationError):
        FeedbackCandidateManifest(
            build_state=FeedbackBuildState.FEEDBACK_CANDIDATE_BUILT,
            feedback_packages=(),
        )
    with pytest.raises(ValidationError):
        FeedbackCandidateManifest(
            build_state=FeedbackBuildState.FEEDBACK_CANDIDATE_BUILT,
            feedback_packages=(package, package),
        )
    decision = FeedbackValidationDecision(
        feedback_id=package.feedback_id,
        state=FeedbackValidationState.VALIDATED_FOR_FUTURE_CYCLE,
        requires_p0_authorization=False,
    )
    with pytest.raises(ValidationError):
        ValidatedNextCycleFeedbackManifest(
            accepted=(package,),
            rejected=(package,),
            reserved=(),
            decisions=(decision,),
        )
    with pytest.raises(ValidationError):
        ValidatedNextCycleFeedbackManifest(
            accepted=(package,),
            rejected=(),
            reserved=(),
            decisions=(),
        )

    _invalid(valid_input_bundle, champion_configuration_id="missing")
    _invalid(valid_input_bundle, challenger_configuration_ids=("missing",))
    _invalid(
        valid_input_bundle,
        challenger_configuration_ids=(valid_input_bundle.champion_configuration_id,),
    )
    challenger = valid_input_bundle.challenger_configuration_ids[0]
    _invalid(valid_input_bundle, challenger_configuration_ids=(challenger, challenger))
    _invalid(valid_input_bundle, upstream_bundle_refs=())
    other_ref = artifact_ref().model_copy(
        update={"cycle": CycleRef(cycle_id="other", ordinal=6)}
    )
    _invalid(
        valid_input_bundle,
        upstream_bundle_refs=(artifact_ref(), other_ref),
    )


def valid_feedback_package():
    from quant_pipeline.phase_09.subphases.s09_competition_promotion.models import (
        P9P6SynthesisFeedback,
    )

    return P9P6SynthesisFeedback(
        feedback_id="fb",
        source_cycle=CycleRef(cycle_id="c1", ordinal=1),
        target_cycle=CycleRef(cycle_id="c2", ordinal=2),
        target_policy_id="p6-pricing",
        target_policy_version="1.0.0",
        feedback_type="pricing_review",
        effect_type=FeedbackEffectType.RESEARCH_REQUEST,
        evidence_refs=(evidence("fb-evidence"),),
        confidence=0.9,
        economic_materiality=1.0,
        expires_after_cycle=CycleRef(cycle_id="c3", ordinal=3),
    )


def test_qualification_and_execution_envelope_validators(valid_input_bundle) -> None:
    qualification = ChallengerQualification(
        challenger_configuration_id="challenger-a",
        state=ChallengerQualificationState.RETAIN_CHAMPION,
        effect_size=0.0,
        probability_of_superiority=0.5,
        contamination_state=ContaminationState.CLEAN,
    )
    with pytest.raises(ValidationError):
        ChampionChallengerQualificationReport(
            champion_configuration_id="champion",
            cohort_id="c",
            qualifications=(qualification,),
            recommended_challenger_id="other",
            report_state=ChallengerQualificationState.RETAIN_CHAMPION,
        )

    from quant_pipeline.phase_09.subphases.s09_competition_promotion.service import (
        run_s9_subphase,
    )

    envelope = run_s9_subphase(inputs=valid_input_bundle, created_at=NOW)
    with pytest.raises(ValidationError):
        S9ExecutionEnvelope(payload=envelope.payload, payload_sha256="0" * 64)
