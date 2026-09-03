from __future__ import annotations

from datetime import datetime
from statistics import NormalDist, mean, stdev

from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import ModuleStatus

from .enums import FeedbackLifecycleState, MetricDirection, OutcomeMaturity
from .hashing import sha256_hex
from .models import (
    FeedbackEffectivenessAssessment,
    FeedbackEffectivenessInputBundle,
    FeedbackEffectivenessModuleOutput,
    FeedbackEffectivenessReport,
    FeedbackLifecycleEvent,
    FeedbackLifecycleLedger,
    FeedbackRegressionPanel,
    FeedbackRegressionRecord,
    ModuleDiagnostics,
    build_module_result,
)

MODULE_ID = "P9.S10.M03"
_MATURE_STATES = {OutcomeMaturity.MATURED, OutcomeMaturity.SETTLED}


def _unique_evidence(values):
    by_id = {value.evidence_id: value for value in values}
    return tuple(sorted(by_id.values(), key=lambda value: value.evidence_id))


def _oriented_effect(direction: MetricDirection, baseline: float, intervention: float) -> float:
    if direction == MetricDirection.MAXIMIZE:
        return intervention - baseline
    return baseline - intervention


def _adverse_guardrail_change(
    direction: MetricDirection,
    baseline: float,
    intervention: float,
) -> float:
    if direction == MetricDirection.MAXIMIZE:
        return max(0.0, baseline - intervention)
    return max(0.0, intervention - baseline)


def _event(
    *,
    feedback_id: str,
    state: FeedbackLifecycleState,
    cycle,
    event_time: datetime,
    reason_codes: tuple[str, ...] = (),
    evidence_refs=(),
) -> FeedbackLifecycleEvent:
    event_id = "feedback-event-" + sha256_hex(
        {
            "feedback_id": feedback_id,
            "state": state,
            "cycle": cycle,
            "event_time": event_time,
            "reason_codes": reason_codes,
        }
    )[:24]
    return FeedbackLifecycleEvent(
        event_id=event_id,
        feedback_id=feedback_id,
        state=state,
        cycle=cycle,
        event_time=event_time,
        reason_codes=reason_codes,
        evidence_refs=tuple(evidence_refs),
    )


def evaluate_feedback_effectiveness(
    *,
    inputs: FeedbackEffectivenessInputBundle,
    evaluated_at: datetime,
):
    accepted_ids = {package.feedback_id for package in inputs.validated_feedback_manifest.accepted}
    authorization_by_id = {record.feedback_id: record for record in inputs.authorizations}
    activation_by_id = {record.feedback_id: record for record in inputs.activations}
    outcomes_by_id: dict[str, list] = {}
    for observation in inputs.outcome_pairs:
        outcomes_by_id.setdefault(observation.feedback_id, []).append(observation)
    guardrails_by_id: dict[str, list] = {}
    for observation in inputs.guardrail_observations:
        guardrails_by_id.setdefault(observation.feedback_id, []).append(observation)

    previous_events = (
        list(inputs.previous_lifecycle_ledger.events)
        if inputs.previous_lifecycle_ledger is not None
        else []
    )
    existing_event_ids = {event.event_id for event in previous_events}
    new_events: list[FeedbackLifecycleEvent] = []
    assessments: list[FeedbackEffectivenessAssessment] = []
    regressions: list[FeedbackRegressionRecord] = []

    for package in sorted(inputs.feedback_packages, key=lambda item: item.feedback_id):
        feedback_id = package.feedback_id
        activation = activation_by_id.get(feedback_id)
        authorization = authorization_by_id.get(feedback_id)
        reason_codes: tuple[str, ...] = ()
        evidence_refs = tuple(package.evidence_refs)
        metric_id: str | None = None
        sample_size = 0
        mean_effect: float | None = None
        standard_error: float | None = None
        lower: float | None = None
        upper: float | None = None
        policy_diff_sha256: str | None = None
        confounded = False
        guardrail_ids: tuple[str, ...] = ()

        if feedback_id not in accepted_ids:
            state = FeedbackLifecycleState.NOT_ACTIVATED
            reason_codes = ("P9_FEEDBACK_NOT_IN_ACCEPTED_PARTITION",)
        elif activation is None or not activation.activated:
            state = FeedbackLifecycleState.NOT_ACTIVATED
            reason_codes = ("P9_FEEDBACK_ACTIVATION_MISSING",)
        elif activation.reverted:
            state = FeedbackLifecycleState.REVERTED
            reason_codes = ("P9_FEEDBACK_REVERTED",)
            policy_diff_sha256 = sha256_hex(activation.exact_policy_diff)
        elif authorization is None or not authorization.authorized:
            state = FeedbackLifecycleState.INVALID
            reason_codes = ("P9_FEEDBACK_AUTHORIZATION_MISSING",)
            policy_diff_sha256 = sha256_hex(activation.exact_policy_diff)
        else:
            policy_diff_sha256 = sha256_hex(activation.exact_policy_diff)
            metric_id = activation.target_metric_id
            metric_policy = inputs.evaluation_policy.resolve(metric_id)
            if metric_policy is None:
                state = FeedbackLifecycleState.INCONCLUSIVE
                reason_codes = ("P9_FEEDBACK_METRIC_POLICY_MISSING",)
            else:
                observations = [
                    observation
                    for observation in outcomes_by_id.get(feedback_id, [])
                    if observation.metric_id == metric_id
                    and observation.comparable
                    and observation.maturity in _MATURE_STATES
                ]
                pending_observations = [
                    observation
                    for observation in outcomes_by_id.get(feedback_id, [])
                    if observation.metric_id == metric_id
                    and observation.maturity not in _MATURE_STATES
                ]
                if not observations:
                    state = FeedbackLifecycleState.OUTCOME_NOT_MATURED
                    reason_codes = ("P9_FEEDBACK_OUTCOME_NOT_MATURED",)
                    if not pending_observations:
                        reason_codes = ("P9_FEEDBACK_OUTCOME_MISSING",)
                else:
                    confounded = bool(activation.simultaneous_feedback_ids)
                    effects = [
                        _oriented_effect(
                            metric_policy.direction,
                            observation.baseline_value,
                            observation.intervention_value,
                        )
                        for observation in observations
                    ]
                    sample_size = len(effects)
                    mean_effect = mean(effects)
                    standard_error = (
                        stdev(effects) / (sample_size**0.5) if sample_size > 1 else 0.0
                    )
                    z_value = NormalDist().inv_cdf(
                        0.5 + metric_policy.confidence_level / 2.0
                    )
                    lower = mean_effect - z_value * standard_error
                    upper = mean_effect + z_value * standard_error
                    evidence_refs = _unique_evidence(
                        evidence_refs
                        + tuple(
                            evidence
                            for observation in observations
                            for evidence in observation.evidence_refs
                        )
                    )

                    feedback_regressions: list[FeedbackRegressionRecord] = []
                    for guardrail in guardrails_by_id.get(feedback_id, []):
                        adverse = _adverse_guardrail_change(
                            guardrail.direction,
                            guardrail.baseline_value,
                            guardrail.intervention_value,
                        )
                        if adverse > guardrail.maximum_allowed_regression:
                            record = FeedbackRegressionRecord(
                                feedback_id=feedback_id,
                                guardrail_id=guardrail.guardrail_id,
                                adverse_change=adverse,
                                critical=guardrail.critical,
                                evidence_refs=guardrail.evidence_refs,
                            )
                            feedback_regressions.append(record)
                            regressions.append(record)
                    guardrail_ids = tuple(
                        sorted(record.guardrail_id for record in feedback_regressions)
                    )
                    critical_regression = any(record.critical for record in feedback_regressions)
                    if critical_regression:
                        state = FeedbackLifecycleState.REGRESSIVE
                        reason_codes = ("P9_FEEDBACK_CRITICAL_GUARDRAIL_REGRESSION",)
                    elif confounded and inputs.evaluation_policy.reject_unisolated_interventions:
                        state = FeedbackLifecycleState.INCONCLUSIVE
                        reason_codes = ("P9_FEEDBACK_INTERVENTION_CONFOUNDED",)
                    elif sample_size < metric_policy.minimum_observations:
                        state = FeedbackLifecycleState.INCONCLUSIVE
                        reason_codes = ("P9_FEEDBACK_SAMPLE_INSUFFICIENT",)
                    elif lower >= metric_policy.minimum_material_effect:
                        state = FeedbackLifecycleState.EFFECTIVE
                    elif upper < metric_policy.minimum_material_effect:
                        state = FeedbackLifecycleState.INEFFECTIVE
                    else:
                        state = FeedbackLifecycleState.INCONCLUSIVE
                        reason_codes = ("P9_FEEDBACK_EFFECT_UNCERTAIN",)

        assessment = FeedbackEffectivenessAssessment(
            feedback_id=feedback_id,
            state=state,
            metric_id=metric_id,
            sample_size=sample_size,
            mean_effect=mean_effect,
            standard_error=standard_error,
            confidence_lower=lower,
            confidence_upper=upper,
            guardrail_regressions=guardrail_ids,
            policy_diff_sha256=policy_diff_sha256,
            confounded=confounded,
            evidence_refs=evidence_refs,
            reason_codes=reason_codes,
        )
        assessments.append(assessment)
        lifecycle_event = _event(
            feedback_id=feedback_id,
            state=state,
            cycle=inputs.evaluation_cycle,
            event_time=evaluated_at,
            reason_codes=reason_codes,
            evidence_refs=evidence_refs,
        )
        if lifecycle_event.event_id not in existing_event_ids:
            new_events.append(lifecycle_event)
            existing_event_ids.add(lifecycle_event.event_id)

    events = tuple(
        sorted(
            previous_events + new_events,
            key=lambda item: (item.feedback_id, item.cycle.ordinal, item.event_time, item.event_id),
        )
    )
    previous_hash = (
        inputs.previous_lifecycle_ledger.ledger_sha256
        if inputs.previous_lifecycle_ledger is not None
        else None
    )
    ledger_payload = {
        "previous_ledger_sha256": previous_hash,
        "events": events,
    }
    ledger = FeedbackLifecycleLedger(
        previous_ledger_sha256=previous_hash,
        events=events,
        ledger_sha256=sha256_hex(ledger_payload),
    )
    counts = {state: 0 for state in FeedbackLifecycleState}
    for assessment in assessments:
        counts[assessment.state] += 1
    pending_count = (
        counts[FeedbackLifecycleState.OUTCOME_NOT_MATURED]
        + counts[FeedbackLifecycleState.NOT_ACTIVATED]
    )
    classified = {
        FeedbackLifecycleState.EFFECTIVE,
        FeedbackLifecycleState.INEFFECTIVE,
        FeedbackLifecycleState.REGRESSIVE,
        FeedbackLifecycleState.INCONCLUSIVE,
        FeedbackLifecycleState.OUTCOME_NOT_MATURED,
        FeedbackLifecycleState.NOT_ACTIVATED,
    }
    other_count = sum(count for state, count in counts.items() if state not in classified)
    report = FeedbackEffectivenessReport(
        policy_id=inputs.evaluation_policy.policy_id,
        assessments=tuple(assessments),
        effective_count=counts[FeedbackLifecycleState.EFFECTIVE],
        ineffective_count=counts[FeedbackLifecycleState.INEFFECTIVE],
        regressive_count=counts[FeedbackLifecycleState.REGRESSIVE],
        inconclusive_count=counts[FeedbackLifecycleState.INCONCLUSIVE],
        pending_count=pending_count,
        other_count=other_count,
    )
    output = FeedbackEffectivenessModuleOutput(
        report=report,
        lifecycle_ledger=ledger,
        regression_panel=FeedbackRegressionPanel(records=tuple(regressions)),
    )
    limited_states = {
        FeedbackLifecycleState.INCONCLUSIVE,
        FeedbackLifecycleState.OUTCOME_NOT_MATURED,
        FeedbackLifecycleState.NOT_ACTIVATED,
        FeedbackLifecycleState.REVERTED,
    }
    invalid_states = {FeedbackLifecycleState.INVALID}
    states = {assessment.state for assessment in assessments}
    if states & invalid_states:
        status = ModuleStatus.INVALID
        module_reason_codes = ("P9_FEEDBACK_EFFECTIVENESS_INVALID_INPUT",)
    elif states & limited_states:
        status = ModuleStatus.LIMITED
        module_reason_codes = ("P9_FEEDBACK_EFFECTIVENESS_PARTIAL",)
    else:
        status = ModuleStatus.SUCCESS
        module_reason_codes = ()
    all_evidence = _unique_evidence(
        tuple(evidence for assessment in assessments for evidence in assessment.evidence_refs)
    )
    return build_module_result(
        module_id=MODULE_ID,
        status=status,
        output=output,
        diagnostics=ModuleDiagnostics(
            counters=(
                ("feedback_count", len(assessments)),
                ("effective_count", report.effective_count),
                ("ineffective_count", report.ineffective_count),
                ("regressive_count", report.regressive_count),
                ("inconclusive_count", report.inconclusive_count),
                ("pending_count", report.pending_count),
            ),
            trace=(
                "feedback effects were evaluated only after authorization and activation",
                "critical guardrail regressions override target-metric improvements",
            ),
        ),
        evidence_refs=all_evidence,
        reason_codes=module_reason_codes,
    )
