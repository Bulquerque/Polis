from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from quant_pipeline.phase_09.contracts.integrity import payload_sha256 as boundary_payload_sha256

from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import (
    ChangeOrigin,
    ContaminationState,
    EvidenceQuality,
    FeedbackEffectType,
    FeedbackPhase,
    GateSeverity,
    GateState,
    OptimizationDirection,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion.models import (
    ArtifactReference,
    CategoricalChangeBounds,
    CompetitionObjectiveSpec,
    ConfigurationEvaluationCard,
    CycleRef,
    EvidenceReference,
    FeedbackPolicyRegistry,
    FeedbackPolicyTarget,
    FrontierAxis,
    GateObservation,
    HardGateRule,
    LeaderboardPolicy,
    MetricValue,
    NumericChangeBounds,
    PairwiseComparisonEvidence,
    ParameterDimension,
    ParameterSpaceRegistry,
    ParameterValue,
    PromotionEvidenceInputBundle,
    PromotionSourceContext,
    PromotionGateReceipt,
    build_promotion_gate_receipt,
    RootCauseEvidence,
    SoftPenaltyRule,
    SubmissionChange,
    SubmissionRecord,
    TargetCapabilitySnapshot,
    TieBreakerRule,
)

H = "a" * 64
NOW = datetime(2026, 8, 3, 18, 0, tzinfo=UTC)


def artifact_ref() -> ArtifactReference:
    return ArtifactReference(
        artifact_id="attribution-reconciliation-bundle",
        artifact_role="ATTRIBUTION_RECONCILIATION_BUNDLE_V1",
        schema_name="p9_attribution_reconciliation_bundle",
        schema_version="1.0.0",
        schema_sha256=H,
        payload_sha256=H,
        producer_module_id="P9.S8.M08",
        run_id="run-1",
        cycle=CycleRef(cycle_id="cycle-5", ordinal=5),
        available_at=NOW - timedelta(hours=1),
        location="artifact://run-1/attribution-reconciliation-bundle",
    )


def evidence(
    evidence_id: str = "ev-1",
    quality: EvidenceQuality = EvidenceQuality.FACTUAL_OBSERVED,
) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=evidence_id,
        artifact_ref=artifact_ref(),
        quality=quality,
        summary="independently produced upstream evidence",
    )


def objective_spec() -> CompetitionObjectiveSpec:
    return CompetitionObjectiveSpec(
        policy_id="competition-policy",
        policy_version="1.0.0",
        primary_score_id="competition_score",
        primary_score_version="1.0.0",
        primary_direction=OptimizationDirection.MAXIMIZE,
        hard_gates=(
            HardGateRule(gate_id="integrity"),
            HardGateRule(gate_id="statistical"),
        ),
        soft_penalties=(
            SoftPenaltyRule(
                metric_id="max_drawdown",
                direction=OptimizationDirection.MINIMIZE,
                weight=0.2,
                reference_value=0.10,
                scale=0.10,
                cap=1.0,
            ),
            SoftPenaltyRule(
                metric_id="cost_drag",
                direction=OptimizationDirection.MINIMIZE,
                weight=0.1,
                reference_value=0.05,
                scale=0.10,
                cap=1.0,
            ),
        ),
        tie_breakers=(
            TieBreakerRule(
                metric_id="competition_score_lower_bound",
                direction=OptimizationDirection.MAXIMIZE,
                priority=1,
            ),
        ),
        frontier_axes=(
            FrontierAxis(metric_id="competition_score", direction=OptimizationDirection.MAXIMIZE),
            FrontierAxis(metric_id="max_drawdown", direction=OptimizationDirection.MINIMIZE),
        ),
        minimum_effect_size=0.05,
        minimum_probability_of_superiority=0.90,
        maximum_pbo=0.40,
        minimum_dsr=0.60,
        maximum_complexity_increase_without_material_gain=0.25,
        allowed_deployment_stages=("SHADOW_ONLY", "LIMITED_CAPITAL", "FULL_PRODUCTION"),
        committed_at=NOW - timedelta(days=2),
        evaluation_started_at=NOW - timedelta(days=1),
        supported_metric_versions=("1.0.0",),
    )


def card(
    configuration_id: str,
    *,
    score: float,
    lower: float,
    drawdown: float,
    cost: float,
    lookback: int,
    complexity: float,
    live: bool = True,
    degraded: bool = False,
    cohort: str = "cohort-a",
) -> ConfigurationEvaluationCard:
    return ConfigurationEvaluationCard(
        configuration_id=configuration_id,
        cohort_id=cohort,
        parameters=(
            ParameterValue(name="lookback", value=lookback),
            ParameterValue(name="model_family", value="ridge"),
        ),
        metrics=(
            MetricValue(metric_id="competition_score", value=score, unit="score"),
            MetricValue(metric_id="competition_score_lower_bound", value=lower, unit="score"),
            MetricValue(metric_id="max_drawdown", value=drawdown, unit="decimal"),
            MetricValue(metric_id="cost_drag", value=cost, unit="decimal"),
        ),
        gates=(
            GateObservation(gate_id="integrity", state=GateState.PASS),
            GateObservation(gate_id="statistical", state=GateState.PASS),
        ),
        model_confidence_set_member=True,
        complexity_score=complexity,
        pbo=0.10,
        dsr=0.90,
        contamination_state=ContaminationState.CLEAN,
        live_evidence_available=live,
        live_degradation_detected=degraded,
        capacity_feasible=True,
        stress_resilient=True,
    )


def configuration_cards() -> tuple[ConfigurationEvaluationCard, ...]:
    return (
        card(
            "champion",
            score=1.00,
            lower=0.80,
            drawdown=0.15,
            cost=0.10,
            lookback=5,
            complexity=0.20,
        ),
        card(
            "challenger-a",
            score=1.20,
            lower=1.02,
            drawdown=0.12,
            cost=0.08,
            lookback=10,
            complexity=0.25,
        ),
        card(
            "challenger-b",
            score=1.18,
            lower=1.00,
            drawdown=0.11,
            cost=0.08,
            lookback=11,
            complexity=0.24,
        ),
        card(
            "challenger-c",
            score=1.16,
            lower=0.98,
            drawdown=0.10,
            cost=0.07,
            lookback=12,
            complexity=0.23,
        ),
    )


def parameter_space() -> ParameterSpaceRegistry:
    return ParameterSpaceRegistry(
        schema_version="1.0.0",
        dimensions=(
            ParameterDimension(name="lookback", numeric_minimum=1.0, numeric_maximum=100.0),
            ParameterDimension(name="model_family", allowed_categories=("ridge", "tree")),
        ),
    )


def pairwise() -> tuple[PairwiseComparisonEvidence, ...]:
    return tuple(
        PairwiseComparisonEvidence(
            champion_configuration_id="champion",
            challenger_configuration_id=cid,
            cohort_id="cohort-a",
            effect_size=effect,
            effect_lower_bound=effect - 0.05,
            effect_upper_bound=effect + 0.05,
            probability_of_superiority=0.96,
            paired_bootstrap_available=True,
            anytime_valid_state="CHALLENGER_SUPERIOR",
            live_comparison_available=True,
            live_effect_size=effect - 0.02,
            live_degradation_detected=False,
            evidence_refs=(evidence(f"ev-{cid}"),),
        )
        for cid, effect in (("challenger-a", 0.20), ("challenger-b", 0.18), ("challenger-c", 0.16))
    )


def gate_receipts() -> tuple[PromotionGateReceipt, ...]:
    return (
        build_promotion_gate_receipt(
            gate_id="integrity", run_id="run-1", cycle=SOURCE_CYCLE if "SOURCE_CYCLE" in globals() else CycleRef(cycle_id="cycle-5", ordinal=5),
            subject_configuration_ids=("challenger-a", "challenger-b", "challenger-c"), source_bundle_sha256=H, producer_module_id="P9.S9.GATE.INTEGRITY",
            state=GateState.PASS, severity=GateSeverity.CRITICAL,
            evidence_refs=(evidence("ev-integrity"),), reason_codes=(), limitations=(),
        ),
        build_promotion_gate_receipt(
            gate_id="statistical", run_id="run-1", cycle=SOURCE_CYCLE if "SOURCE_CYCLE" in globals() else CycleRef(cycle_id="cycle-5", ordinal=5),
            subject_configuration_ids=("challenger-a", "challenger-b", "challenger-c"), source_bundle_sha256=H, producer_module_id="P9.S9.GATE.STATISTICAL",
            state=GateState.PASS, severity=GateSeverity.BLOCKING,
            evidence_refs=(evidence("ev-statistical"),), reason_codes=(), limitations=(),
        ),
    )


def feedback_registry() -> FeedbackPolicyRegistry:
    return FeedbackPolicyRegistry(
        registry_version="1.0.0",
        targets=(
            FeedbackPolicyTarget(
                target_phase=FeedbackPhase.P5,
                target_policy_id="p5-calibration",
                target_policy_version="1.0.0",
                allowed_feedback_types=("calibration",),
                numeric_bounds=(
                    NumericChangeBounds(
                        parameter_name="confidence_floor",
                        minimum=0.5,
                        maximum=0.99,
                        maximum_absolute_delta=0.1,
                    ),
                ),
                requires_p0_authorization_for=(FeedbackEffectType.POLICY_BOUND_CHANGE,),
            ),
            FeedbackPolicyTarget(
                target_phase=FeedbackPhase.P6,
                target_policy_id="p6-pricing",
                target_policy_version="1.0.0",
                allowed_feedback_types=("pricing_review",),
                numeric_bounds=(
                    NumericChangeBounds(
                        parameter_name="cost_buffer",
                        minimum=0.0,
                        maximum=0.5,
                        maximum_absolute_delta=0.05,
                    ),
                ),
                requires_p0_authorization_for=(FeedbackEffectType.POLICY_BOUND_CHANGE,),
            ),
            FeedbackPolicyTarget(
                target_phase=FeedbackPhase.P7,
                target_policy_id="p7-abstention",
                target_policy_version="1.0.0",
                allowed_feedback_types=("abstention_review",),
                categorical_bounds=(
                    CategoricalChangeBounds(
                        parameter_name="mode",
                        allowed_values=("strict", "balanced"),
                    ),
                ),
            ),
            FeedbackPolicyTarget(
                target_phase=FeedbackPhase.P8,
                target_policy_id="p8-capacity",
                target_policy_version="1.0.0",
                allowed_feedback_types=("capacity_review",),
                numeric_bounds=(
                    NumericChangeBounds(
                        parameter_name="participation_limit",
                        minimum=0.0,
                        maximum=0.2,
                        maximum_absolute_delta=0.02,
                    ),
                ),
                requires_p0_authorization_for=(FeedbackEffectType.POLICY_BOUND_CHANGE,),
            ),
        ),
    )


def root_causes() -> tuple[RootCauseEvidence, ...]:
    return (
        RootCauseEvidence(
            root_cause_id="cause-p6",
            target_phase=FeedbackPhase.P6,
            target_policy_id="p6-pricing",
            feedback_type="pricing_review",
            effect_type=FeedbackEffectType.POLICY_BOUND_CHANGE,
            summary="execution attribution indicates under-estimated costs in P6 pricing",
            evidence_refs=(evidence("ev-root-p6"),),
            evidence_quality=EvidenceQuality.FACTUAL_EXECUTED,
            confidence=0.93,
            economic_materiality=0.12,
            numeric_change_bounds=(
                NumericChangeBounds(
                    parameter_name="cost_buffer",
                    minimum=0.05,
                    maximum=0.15,
                    maximum_absolute_delta=0.03,
                ),
            ),
            atomic_group_id="pricing-capacity",
        ),
        RootCauseEvidence(
            root_cause_id="cause-p8",
            target_phase=FeedbackPhase.P8,
            target_policy_id="p8-capacity",
            feedback_type="capacity_review",
            effect_type=FeedbackEffectType.POLICY_BOUND_CHANGE,
            summary="capacity attribution indicates an overly permissive participation bound",
            evidence_refs=(evidence("ev-root-p8"),),
            evidence_quality=EvidenceQuality.FACTUAL_EXECUTED,
            confidence=0.91,
            economic_materiality=0.10,
            numeric_change_bounds=(
                NumericChangeBounds(
                    parameter_name="participation_limit",
                    minimum=0.01,
                    maximum=0.12,
                    maximum_absolute_delta=0.01,
                ),
            ),
            atomic_group_id="pricing-capacity",
        ),
    )


def capabilities() -> tuple[TargetCapabilitySnapshot, ...]:
    registry = feedback_registry()
    return tuple(
        TargetCapabilitySnapshot(
            target_phase=target.target_phase,
            target_policy_id=target.target_policy_id,
            target_policy_version=target.target_policy_version,
            available=True,
            accepted_contract_major=1,
        )
        for target in registry.targets
    )


def promotion_source_context(*, cards, ref):
    values = {
        "run_id": ref.run_id,
        "cycle": ref.cycle,
        "attribution_bundle_sha256": H,
        "configuration_ids": tuple(card.configuration_id for card in cards),
    }
    return PromotionSourceContext(
        **values,
        context_sha256=boundary_payload_sha256(
            {
                "contract_name": "CONTRACT_P9_S8_TO_S9_PROMOTION_EVIDENCE_V2",
                "contract_version": "2.0.0",
                **values,
            }
        ),
    )


@pytest.fixture
def valid_input_bundle() -> PromotionEvidenceInputBundle:
    cards = configuration_cards()
    ref = artifact_ref()
    return PromotionEvidenceInputBundle(
        upstream_bundle_refs=(ref,),
        source_context=promotion_source_context(cards=cards, ref=ref),
        objective_spec=objective_spec(),
        configurations=cards,
        parameter_space=parameter_space(),
        model_confidence_set_ids=tuple(card.configuration_id for card in cards),
        submission_ledger=(),
        leaderboard_policy=LeaderboardPolicy(
            policy_id="leaderboard-policy",
            maximum_submissions=10,
            information_budget=10.0,
            base_submission_cost=1.0,
            uncommitted_penalty=2.0,
            public_reaction_penalty=3.0,
            change_magnitude_weight=1.0,
            contamination_threshold=7.0,
            limited_use_threshold=4.0,
        ),
        champion_configuration_id="champion",
        challenger_configuration_ids=("challenger-a", "challenger-b", "challenger-c"),
        pairwise_evidence=pairwise(),
        promotion_gate_receipts=gate_receipts(),
        root_causes=root_causes(),
        feedback_policy_registry=feedback_registry(),
        target_capabilities=capabilities(),
    )


@pytest.fixture
def public_reaction_submission() -> SubmissionRecord:
    return SubmissionRecord(
        submission_id="sub-2",
        configuration_id="challenger-a",
        submitted_at=NOW,
        hypothesis_committed_at=NOW - timedelta(hours=1),
        hypothesis_text_hash=H,
        public_score=1.2,
        parent_submission_id="sub-1",
        changes_after_parent=(
            SubmissionChange(
                parameter_name="lookback",
                normalized_magnitude=0.5,
                origin=ChangeOrigin.PUBLIC_SCORE_REACTION,
                rationale="changed after public score",
            ),
        ),
    )
