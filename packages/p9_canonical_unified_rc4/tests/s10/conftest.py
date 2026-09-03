from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from quant_pipeline.phase_09.contracts.integrity import payload_sha256 as boundary_payload_sha256

from quant_pipeline.phase_09.subphases.s09_competition_promotion import (
    CycleRef,
    NumericChangeBounds,
    RootCauseEvidence,
    build_typed_feedback,
    run_s9_subphase,
    validate_feedback_for_future_activation,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import (
    ContaminationState,
    EvidenceQuality,
    FeedbackEffectType,
    FeedbackPhase,
    GateSeverity,
    GateState,
    ModuleStatus,
    OptimizationDirection,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion.models import (
    ArtifactReference,
    CategoricalChangeBounds,
    CompetitionObjectiveSpec,
    ConfigurationEvaluationCard,
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
    SoftPenaltyRule,
    TargetCapabilitySnapshot,
    TieBreakerRule,
)
from quant_pipeline.phase_09.subphases.s10_memory_release import (
    CausalStatus,
    MetricDirection,
    OutcomeMaturity,
    ResearchItemType,
)
from quant_pipeline.phase_09.subphases.s10_memory_release.hashing import sha256_hex
from quant_pipeline.phase_09.subphases.s10_memory_release.models import (
    BuildEnvironment,
    ConsumerReceiptReference,
    FeedbackActivationRecord,
    FeedbackAuthorizationRecord,
    FeedbackEffectivenessInputBundle,
    FeedbackEvaluationPolicy,
    FeedbackOutcomePair,
    GuardrailObservation,
    MetricEvaluationPolicy,
    PolicyChange,
    ResearchClaimCandidate,
    ResearchMemoryUpdatePolicy,
    ResearchNormalizationPolicy,
    ResearchScope,
    S10InputBundle,
    SubphaseReceiptReference,
    TestSummary,
)

H = "a" * 64
NOW = datetime(2026, 8, 3, 18, 0, tzinfo=UTC)
SOURCE_CYCLE = CycleRef(cycle_id="cycle-5", ordinal=5)


def artifact_ref(
    artifact_id: str = "attribution-reconciliation-bundle",
    role: str = "ATTRIBUTION_RECONCILIATION_BUNDLE_V1",
    producer_module_id: str = "P9.S8.M08",
    cycle: CycleRef = SOURCE_CYCLE,
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=artifact_id,
        artifact_role=role,
        schema_name=role.lower(),
        schema_version="1.0.0",
        schema_sha256=H,
        payload_sha256=H,
        producer_module_id=producer_module_id,
        run_id="run-1",
        cycle=cycle,
        available_at=NOW - timedelta(hours=1),
        location=f"artifact://run-1/{artifact_id}",
    )


def evidence(
    evidence_id: str = "ev-1",
    quality: EvidenceQuality = EvidenceQuality.FACTUAL_OBSERVED,
) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=evidence_id,
        artifact_ref=artifact_ref(artifact_id=f"artifact-{evidence_id}"),
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
        ),
        tie_breakers=(
            TieBreakerRule(
                metric_id="competition_score_lower_bound",
                direction=OptimizationDirection.MAXIMIZE,
                priority=1,
            ),
        ),
        frontier_axes=(
            FrontierAxis(
                metric_id="competition_score",
                direction=OptimizationDirection.MAXIMIZE,
            ),
            FrontierAxis(
                metric_id="max_drawdown",
                direction=OptimizationDirection.MINIMIZE,
            ),
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


def card(configuration_id: str, score: float, lower: float, lookback: int):
    return ConfigurationEvaluationCard(
        configuration_id=configuration_id,
        cohort_id="cohort-a",
        parameters=(
            ParameterValue(name="lookback", value=lookback),
            ParameterValue(name="model_family", value="ridge"),
        ),
        metrics=(
            MetricValue(metric_id="competition_score", value=score, unit="score"),
            MetricValue(
                metric_id="competition_score_lower_bound",
                value=lower,
                unit="score",
            ),
            MetricValue(metric_id="max_drawdown", value=0.10, unit="decimal"),
        ),
        gates=(
            GateObservation(gate_id="integrity", state=GateState.PASS),
            GateObservation(gate_id="statistical", state=GateState.PASS),
        ),
        model_confidence_set_member=True,
        complexity_score=0.2,
        pbo=0.10,
        dsr=0.90,
        contamination_state=ContaminationState.CLEAN,
        live_evidence_available=True,
        live_degradation_detected=False,
        capacity_feasible=True,
        stress_resilient=True,
    )


def feedback_registry() -> FeedbackPolicyRegistry:
    return FeedbackPolicyRegistry(
        registry_version="1.0.0",
        targets=(
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
            summary="under-estimated transaction costs",
            evidence_refs=(evidence("ev-root-p6", EvidenceQuality.FACTUAL_EXECUTED),),
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
            summary="participation limit was too permissive",
            evidence_refs=(evidence("ev-root-p8", EvidenceQuality.FACTUAL_EXECUTED),),
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
    return tuple(
        TargetCapabilitySnapshot(
            target_phase=target.target_phase,
            target_policy_id=target.target_policy_id,
            target_policy_version=target.target_policy_version,
            available=True,
            accepted_contract_major=1,
        )
        for target in feedback_registry().targets
    )


def current_s9_envelope():
    cards = (
        card("champion", 1.00, 0.80, 5),
        card("challenger-a", 1.20, 1.02, 10),
        card("challenger-b", 1.18, 1.00, 11),
    )
    pairwise = tuple(
        PairwiseComparisonEvidence(
            champion_configuration_id="champion",
            challenger_configuration_id=challenger,
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
            evidence_refs=(evidence(f"ev-{challenger}"),),
        )
        for challenger, effect in (("challenger-a", 0.20), ("challenger-b", 0.18))
    )
    gates = (
        build_promotion_gate_receipt(
            gate_id="integrity",
            run_id="run-1",
            cycle=SOURCE_CYCLE,
            subject_configuration_ids=("challenger-a", "challenger-b"),
            source_bundle_sha256=H,
            producer_module_id="P9.S9.GATE.INTEGRITY",
            state=GateState.PASS,
            severity=GateSeverity.CRITICAL,
            evidence_refs=(evidence("ev-integrity"),),
            reason_codes=(),
            limitations=(),
        ),
        build_promotion_gate_receipt(
            gate_id="statistical",
            run_id="run-1",
            cycle=SOURCE_CYCLE,
            subject_configuration_ids=("challenger-a", "challenger-b"),
            source_bundle_sha256=H,
            producer_module_id="P9.S9.GATE.STATISTICAL",
            state=GateState.PASS,
            severity=GateSeverity.BLOCKING,
            evidence_refs=(evidence("ev-statistical"),),
            reason_codes=(),
            limitations=(),
        ),
    )
    ref = artifact_ref()
    bundle = PromotionEvidenceInputBundle(
        upstream_bundle_refs=(ref,),
        source_context=promotion_source_context(cards=cards, ref=ref),
        objective_spec=objective_spec(),
        configurations=cards,
        parameter_space=ParameterSpaceRegistry(
            schema_version="1.0.0",
            dimensions=(
                ParameterDimension(name="lookback", numeric_minimum=1.0, numeric_maximum=100.0),
                ParameterDimension(name="model_family", allowed_categories=("ridge", "tree")),
            ),
        ),
        model_confidence_set_ids=tuple(item.configuration_id for item in cards),
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
        challenger_configuration_ids=("challenger-a", "challenger-b"),
        pairwise_evidence=pairwise,
        promotion_gate_receipts=gates,
        root_causes=root_causes(),
        feedback_policy_registry=feedback_registry(),
        target_capabilities=capabilities(),
    )
    return run_s9_subphase(inputs=bundle, created_at=NOW)


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


def historical_feedback_input() -> FeedbackEffectivenessInputBundle:
    source_cycle = CycleRef(cycle_id="cycle-3", ordinal=3)
    target_cycle = CycleRef(cycle_id="cycle-4", ordinal=4)
    candidate_result = build_typed_feedback(
        root_causes=root_causes(),
        registry=feedback_registry(),
        previous_effectiveness=(),
        source_cycle=source_cycle,
        target_cycle=target_cycle,
    )
    assert candidate_result.output is not None
    gate_result = validate_feedback_for_future_activation(
        candidate_manifest=candidate_result.output,
        registry=feedback_registry(),
        target_capabilities=capabilities(),
        previous_activation_ledger=(),
        current_cycle=source_cycle,
    )
    assert gate_result.output is not None
    packages = candidate_result.output.feedback_packages
    authorizations = tuple(
        FeedbackAuthorizationRecord(
            feedback_id=package.feedback_id,
            authorization_id=f"auth-{package.feedback_id}",
            authorized=True,
            authorized_at=NOW - timedelta(days=3),
            evidence_refs=package.evidence_refs,
        )
        for package in packages
    )
    activations = tuple(
        FeedbackActivationRecord(
            feedback_id=package.feedback_id,
            activated=True,
            target_cycle=target_cycle,
            activated_at=NOW - timedelta(days=2),
            target_phase=package.target_phase.value,
            target_policy_id=package.target_policy_id,
            target_metric_id="net_competition_score",
            target_policy_version_before="1.0.0",
            target_policy_version_after="1.0.1",
            policy_before_sha256="b" * 64,
            policy_after_sha256="c" * 64,
            exact_policy_diff=(
                PolicyChange(
                    parameter_name="bounded_parameter",
                    before_value="0.10",
                    after_value="0.12",
                ),
            ),
        )
        for package in packages
    )
    observations = tuple(
        FeedbackOutcomePair(
            feedback_id=package.feedback_id,
            pair_id=f"{package.feedback_id}-pair-{index}",
            metric_id="net_competition_score",
            cohort_id="cohort-historical",
            baseline_value=1.0 + index * 0.01,
            intervention_value=1.10 + index * 0.01,
            maturity=OutcomeMaturity.MATURED,
            evidence_refs=package.evidence_refs,
        )
        for package in packages
        for index in range(6)
    )
    return FeedbackEffectivenessInputBundle(
        validated_feedback_manifest=gate_result.output.manifest,
        feedback_packages=packages,
        authorizations=authorizations,
        activations=activations,
        outcome_pairs=observations,
        evaluation_policy=FeedbackEvaluationPolicy(
            policy_id="feedback-effectiveness-policy",
            metrics=(
                MetricEvaluationPolicy(
                    metric_id="net_competition_score",
                    direction=MetricDirection.MAXIMIZE,
                    minimum_material_effect=0.05,
                    minimum_observations=5,
                    confidence_level=0.95,
                ),
            ),
        ),
        evaluation_cycle=SOURCE_CYCLE,
    )


def research_candidates() -> tuple[ResearchClaimCandidate, ...]:
    scope = ResearchScope(
        phases=("P6", "P8"),
        policy_ids=("p6-pricing", "p8-capacity"),
        regimes=("high-cost",),
    )
    return (
        ResearchClaimCandidate(
            candidate_id="claim-supported",
            semantic_key="cost-buffer-underestimation",
            claim="Observed execution costs exceeded the P6 pricing buffer.",
            abstract_claim="Pricing buffers can become insufficient in high-cost regimes.",
            scope=scope,
            outcome_maturity=OutcomeMaturity.SETTLED,
            causal_status=CausalStatus.ATTRIBUTED,
            evidence_for=(evidence("ev-claim-supported", EvidenceQuality.FACTUAL_EXECUTED),),
            confidence=0.95,
            materiality=0.15,
            validity_start=SOURCE_CYCLE,
            source_cycles=(SOURCE_CYCLE,),
        ),
        ResearchClaimCandidate(
            candidate_id="claim-hypothesis",
            semantic_key="capacity-cost-interaction",
            claim="Capacity and cost buffers may interact nonlinearly.",
            abstract_claim="Capacity and cost controls may require joint evaluation.",
            scope=scope,
            outcome_maturity=OutcomeMaturity.MATURED,
            causal_status=CausalStatus.ASSOCIATION,
            evidence_for=(evidence("ev-claim-hypothesis"),),
            evidence_against=(evidence("ev-claim-contrary"),),
            confidence=0.70,
            materiality=0.10,
            validity_start=SOURCE_CYCLE,
            source_cycles=(SOURCE_CYCLE,),
        ),
        ResearchClaimCandidate(
            candidate_id="claim-negative",
            semantic_key="capacity-breakpoint",
            claim="A nearby participation breakpoint caused unacceptable market impact.",
            abstract_claim="Aggressive participation can create a nearby capacity breakpoint.",
            scope=scope,
            item_type_hint=ResearchItemType.BREAKPOINT_MEMORY,
            outcome_maturity=OutcomeMaturity.SETTLED,
            causal_status=CausalStatus.ATTRIBUTED,
            evidence_for=(evidence("ev-claim-negative", EvidenceQuality.FACTUAL_EXECUTED),),
            confidence=0.92,
            materiality=0.20,
            validity_start=SOURCE_CYCLE,
            source_cycles=(SOURCE_CYCLE,),
        ),
        ResearchClaimCandidate(
            candidate_id="claim-immature",
            semantic_key="pending-live-effect",
            claim="A live effect is not yet mature.",
            abstract_claim="More evidence is required before evaluating the live effect.",
            scope=scope,
            outcome_maturity=OutcomeMaturity.NOT_MATURED,
            causal_status=CausalStatus.UNKNOWN,
            evidence_for=(evidence("ev-claim-pending"),),
            confidence=0.50,
            materiality=0.05,
            validity_start=SOURCE_CYCLE,
            source_cycles=(SOURCE_CYCLE,),
        ),
    )


def subphase_receipts() -> tuple[SubphaseReceiptReference, ...]:
    records = []
    for index in range(1, 10):
        subphase_id = f"P9.S{index}"
        ref = artifact_ref(
            artifact_id=f"receipt-{subphase_id.lower().replace('.', '-')}",
            role="subphase_execution_receipt",
            producer_module_id=f"P9.S{index}.M01",
        )
        records.append(
            SubphaseReceiptReference(
                subphase_id=subphase_id,
                status=ModuleStatus.SUCCESS,
                receipt_ref=ref,
                output_sha256=ref.payload_sha256,
            )
        )
    return tuple(records)


def consumer_receipts() -> tuple[ConsumerReceiptReference, ...]:
    contracts = (
        ("P9_FOUNDATION_EXPERIMENT_BUNDLE_V1", "foundation"),
        ("P9_BACKTEST_METRICS_BUNDLE_V1", "backtest-metrics"),
        ("P9_ROBUSTNESS_STRESS_BUNDLE_V1", "robustness-stress"),
        ("P9_PROSPECTIVE_ATTRIBUTION_BUNDLE_V1", "prospective-attribution"),
    )
    return tuple(
        ConsumerReceiptReference(
            consumer_id="PHASE09_RELEASE",
            source_contract_name=contract_name,
            source_contract_version="1.0.0",
            receipt_ref=artifact_ref(
                artifact_id=f"consumer-receipt-{slug}",
                role="consumer_receipt",
                producer_module_id="P9.S9.M01",
            ),
            accepted_count=1,
            rejected_count=0,
            reserved_count=0,
        )
        for contract_name, slug in contracts
    )


def valid_s10_input() -> S10InputBundle:
    return S10InputBundle(
        s9_execution_envelope=current_s9_envelope(),
        research_claim_candidates=research_candidates(),
        normalization_policy=ResearchNormalizationPolicy(
            policy_id="research-normalization-policy"
        ),
        memory_update_policy=ResearchMemoryUpdatePolicy(
            policy_id="research-memory-update-policy"
        ),
        feedback_effectiveness_input=historical_feedback_input(),
        upstream_subphase_receipts=subphase_receipts(),
        consumer_receipts=consumer_receipts(),
        build_environment=BuildEnvironment(
            python_version="3.13.5",
            platform="linux-x86_64",
            pydantic_version="2.13.4",
            s9_distribution_version="0.1.0rc1",
            s10_distribution_version="0.1.0rc1",
            dependency_lock_sha256=H,
        ),
        test_summary=TestSummary(
            total=1,
            passed=1,
            failed=0,
            line_coverage_percent=100.0,
            branch_coverage_percent=100.0,
            report_sha256=H,
        ),
        source_tree_sha256=H,
        s9_wheel_sha256=H,
        s10_wheel_sha256=H,
        test_report_ref=artifact_ref(
            artifact_id="p9-test-report", role="P9_TEST_REPORT",
            producer_module_id="P9.RELEASE.TEST_RUNNER",
        ),
        source_tree_ref=artifact_ref(
            artifact_id="p9-source-tree", role="P9_SOURCE_TREE",
            producer_module_id="P9.RELEASE.SOURCE_TREE",
        ),
        s9_wheel_ref=artifact_ref(
            artifact_id="p9-s9-wheel", role="P9_S9_WHEEL",
            producer_module_id="P9.RELEASE.WHEEL_BUILDER",
        ),
        s10_wheel_ref=artifact_ref(
            artifact_id="p9-s10-wheel", role="P9_S10_WHEEL",
            producer_module_id="P9.RELEASE.WHEEL_BUILDER",
        ),
        source_cycle=SOURCE_CYCLE,
        created_at=NOW,
    )


@pytest.fixture
def s10_input() -> S10InputBundle:
    return valid_s10_input()
