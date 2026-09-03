from __future__ import annotations

from quant_pipeline.phase_09.subphases.s09_competition_promotion import (
    CycleRef,
    EvidenceQuality,
    FeedbackEffectType,
    FeedbackPhase,
    NumericChangeBounds,
    RootCauseEvidence,
    build_typed_feedback,
)

from tests.s09.conftest import evidence, feedback_registry, root_causes


def test_builds_typed_p6_and_p8_feedback() -> None:
    result = build_typed_feedback(
        root_causes=root_causes(),
        registry=feedback_registry(),
        previous_effectiveness=(),
        source_cycle=CycleRef(cycle_id="cycle-5", ordinal=5),
        target_cycle=CycleRef(cycle_id="cycle-6", ordinal=6),
    )
    assert result.output is not None
    assert {package.target_phase for package in result.output.feedback_packages} == {
        FeedbackPhase.P6,
        FeedbackPhase.P8,
    }
    assert all(
        package.target_cycle.ordinal > package.source_cycle.ordinal
        for package in result.output.feedback_packages
    )


def test_model_based_counterfactual_cannot_change_policy() -> None:
    cause = RootCauseEvidence(
        root_cause_id="model-only",
        target_phase=FeedbackPhase.P6,
        target_policy_id="p6-pricing",
        feedback_type="pricing_review",
        effect_type=FeedbackEffectType.POLICY_BOUND_CHANGE,
        summary="model-only estimate",
        evidence_refs=(evidence("ev-model", EvidenceQuality.MODEL_BASED_COUNTERFACTUAL),),
        evidence_quality=EvidenceQuality.MODEL_BASED_COUNTERFACTUAL,
        confidence=0.99,
        economic_materiality=1.0,
        numeric_change_bounds=(
            NumericChangeBounds(
                parameter_name="cost_buffer",
                minimum=0.1,
                maximum=0.2,
                maximum_absolute_delta=0.03,
            ),
        ),
    )
    result = build_typed_feedback(
        root_causes=(cause,),
        registry=feedback_registry(),
        previous_effectiveness=(),
        source_cycle=CycleRef(cycle_id="cycle-5", ordinal=5),
        target_cycle=CycleRef(cycle_id="cycle-6", ordinal=6),
    )
    assert result.output is not None
    assert not result.output.feedback_packages
    assert "model-only" in result.output.rejected_root_cause_ids
