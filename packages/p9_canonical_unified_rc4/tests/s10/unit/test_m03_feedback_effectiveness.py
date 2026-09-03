from __future__ import annotations

from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import ModuleStatus
from quant_pipeline.phase_09.subphases.s10_memory_release import (
    FeedbackLifecycleState,
    MetricDirection,
)
from quant_pipeline.phase_09.subphases.s10_memory_release.m03_feedback_effectiveness import (
    evaluate_feedback_effectiveness,
)
from quant_pipeline.phase_09.subphases.s10_memory_release.models import GuardrailObservation

from tests.s10.conftest import NOW, historical_feedback_input


def test_effective_feedback() -> None:
    result = evaluate_feedback_effectiveness(inputs=historical_feedback_input(), evaluated_at=NOW)
    assert result.output is not None
    assert result.output.report.effective_count == 2
    assert all(
        assessment.state == FeedbackLifecycleState.EFFECTIVE
        for assessment in result.output.report.assessments
    )


def test_ineffective_feedback() -> None:
    inputs = historical_feedback_input()
    outcomes = tuple(
        observation.model_copy(update={"intervention_value": observation.baseline_value})
        for observation in inputs.outcome_pairs
    )
    result = evaluate_feedback_effectiveness(
        inputs=inputs.model_copy(update={"outcome_pairs": outcomes}),
        evaluated_at=NOW,
    )
    assert result.output is not None
    assert result.output.report.ineffective_count == 2


def test_critical_guardrail_regression_overrides_target_improvement() -> None:
    inputs = historical_feedback_input()
    feedback_id = inputs.feedback_packages[0].feedback_id
    guardrail = GuardrailObservation(
        feedback_id=feedback_id,
        guardrail_id="max_drawdown",
        direction=MetricDirection.MINIMIZE,
        baseline_value=0.10,
        intervention_value=0.30,
        maximum_allowed_regression=0.05,
        critical=True,
    )
    result = evaluate_feedback_effectiveness(
        inputs=inputs.model_copy(update={"guardrail_observations": (guardrail,)}),
        evaluated_at=NOW,
    )
    assert result.output is not None
    assessment = next(
        item for item in result.output.report.assessments if item.feedback_id == feedback_id
    )
    assert assessment.state == FeedbackLifecycleState.REGRESSIVE
    assert result.output.regression_panel.records


def test_pending_outcome_stays_pending() -> None:
    inputs = historical_feedback_input()
    outcomes = tuple(
        observation.model_copy(update={"maturity": "NOT_MATURED"})
        for observation in inputs.outcome_pairs
    )
    result = evaluate_feedback_effectiveness(
        inputs=inputs.model_copy(update={"outcome_pairs": outcomes}),
        evaluated_at=NOW,
    )
    assert result.output is not None
    assert result.output.report.pending_count == 2


def test_missing_activation_is_not_effective() -> None:
    inputs = historical_feedback_input()
    result = evaluate_feedback_effectiveness(
        inputs=inputs.model_copy(update={"activations": ()}),
        evaluated_at=NOW,
    )
    assert result.output is not None
    assert all(
        item.state == FeedbackLifecycleState.NOT_ACTIVATED
        for item in result.output.report.assessments
    )


def test_missing_authorization_is_invalid() -> None:
    inputs = historical_feedback_input()
    result = evaluate_feedback_effectiveness(
        inputs=inputs.model_copy(update={"authorizations": ()}),
        evaluated_at=NOW,
    )
    assert result.status == ModuleStatus.INVALID
    assert result.output is not None
    assert all(
        item.state == FeedbackLifecycleState.INVALID
        for item in result.output.report.assessments
    )


def test_simultaneous_feedback_is_inconclusive() -> None:
    inputs = historical_feedback_input()
    first, second = inputs.activations
    activations = (
        first.model_copy(update={"simultaneous_feedback_ids": (second.feedback_id,)}),
        second.model_copy(update={"simultaneous_feedback_ids": (first.feedback_id,)}),
    )
    result = evaluate_feedback_effectiveness(
        inputs=inputs.model_copy(update={"activations": activations}),
        evaluated_at=NOW,
    )
    assert result.output is not None
    assert result.output.report.inconclusive_count == 2


def test_ledger_update_is_idempotent() -> None:
    first = evaluate_feedback_effectiveness(inputs=historical_feedback_input(), evaluated_at=NOW)
    assert first.output is not None
    second_inputs = historical_feedback_input().model_copy(
        update={"previous_lifecycle_ledger": first.output.lifecycle_ledger}
    )
    second = evaluate_feedback_effectiveness(inputs=second_inputs, evaluated_at=NOW)
    assert second.output is not None
    assert len(second.output.lifecycle_ledger.events) == len(first.output.lifecycle_ledger.events)
