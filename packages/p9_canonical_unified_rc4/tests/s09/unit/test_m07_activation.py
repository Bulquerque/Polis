from __future__ import annotations

from quant_pipeline.phase_09.subphases.s09_competition_promotion import (
    CycleRef,
    FeedbackActivationLedgerEntry,
    FeedbackValidationState,
    build_typed_feedback,
    validate_feedback_for_future_activation,
)

from tests.s09.conftest import capabilities, feedback_registry, root_causes


def candidate_manifest():
    result = build_typed_feedback(
        root_causes=root_causes(),
        registry=feedback_registry(),
        previous_effectiveness=(),
        source_cycle=CycleRef(cycle_id="cycle-5", ordinal=5),
        target_cycle=CycleRef(cycle_id="cycle-6", ordinal=6),
    )
    assert result.output is not None
    return result.output


def test_valid_feedback_stays_pending_p0() -> None:
    result = validate_feedback_for_future_activation(
        candidate_manifest=candidate_manifest(),
        registry=feedback_registry(),
        target_capabilities=capabilities(),
        previous_activation_ledger=(),
        current_cycle=CycleRef(cycle_id="cycle-5", ordinal=5),
    )
    assert result.output is not None
    assert result.output.pending_p0_count == 2
    assert all(
        decision.state == FeedbackValidationState.VALIDATED_PENDING_P0
        for decision in result.output.manifest.decisions
    )


def test_duplicate_feedback_is_rejected_atomically() -> None:
    manifest = candidate_manifest()
    duplicate_id = manifest.feedback_packages[0].feedback_id
    ledger = (
        FeedbackActivationLedgerEntry(
            feedback_id=duplicate_id,
            state=FeedbackValidationState.VALIDATED_PENDING_P0,
            target_cycle=CycleRef(cycle_id="cycle-6", ordinal=6),
        ),
    )
    result = validate_feedback_for_future_activation(
        candidate_manifest=manifest,
        registry=feedback_registry(),
        target_capabilities=capabilities(),
        previous_activation_ledger=ledger,
        current_cycle=CycleRef(cycle_id="cycle-5", ordinal=5),
    )
    assert result.output is not None
    assert result.output.rejected_count == 2
