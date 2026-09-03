"""P9.S7.M07 — live health, degradation, and rollback recommendation gate."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from .canonical import payload_sha256
from .contracts import NonEmptyStr, StrictModel
from .m05_drift import CrossChannelAgreement
from .m06_sequential import ComparisonState, SequentialModelSet


class LiveHealthState(StrEnum):
    HEALTHY = "HEALTHY"
    WATCH = "WATCH"
    DEGRADED = "DEGRADED"
    REQUALIFICATION_REQUIRED = "REQUALIFICATION_REQUIRED"
    ROLLBACK_RECOMMENDED = "ROLLBACK_RECOMMENDED"
    QUARANTINE_RECOMMENDED = "QUARANTINE_RECOMMENDED"
    INSUFFICIENT_LIVE_EVIDENCE = "INSUFFICIENT_LIVE_EVIDENCE"


class LiveExecutionMetrics(StrictModel):
    observation_count: int = Field(ge=0)
    realized_net_alpha: float | None
    reference_net_alpha: float | None
    mean_cost_error_bps: float | None
    capacity_ratio_to_approved: float | None = Field(default=None, ge=0.0)
    hard_risk_breach_codes: tuple[NonEmptyStr, ...] = ()


class StressCapacityQualification(StrictModel):
    qualification_state: NonEmptyStr
    reverse_stress_distance: float | None = Field(default=None, ge=0.0)
    capacity_limit_ratio: float | None = Field(default=None, ge=0.0)
    hard_blocking_reason_codes: tuple[NonEmptyStr, ...] = ()


class RollbackPolicy(StrictModel):
    minimum_live_observations: int = Field(default=30, ge=1)
    alpha_decay_threshold: float = Field(default=0.0)
    cost_error_watch_bps: float = Field(default=5.0, ge=0.0)
    cost_error_rollback_bps: float = Field(default=20.0, ge=0.0)
    minimum_capacity_ratio: float = Field(default=0.8, gt=0.0)
    severe_capacity_ratio: float = Field(default=0.5, gt=0.0)
    confirmed_drift_action: LiveHealthState = LiveHealthState.REQUALIFICATION_REQUIRED


class DecisionTraceItem(StrictModel):
    rule_id: NonEmptyStr
    triggered: bool
    observed_value: float | None = None
    threshold_value: float | None = None
    reason_code: NonEmptyStr | None = None


class RollbackRecommendation(StrictModel):
    state: LiveHealthState
    decision_trace: tuple[DecisionTraceItem, ...]
    reason_codes: tuple[NonEmptyStr, ...]
    recommendation_only: bool = True
    p0_authorization_required: bool = True
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def evaluate_live_health(
    execution: LiveExecutionMetrics,
    drift: CrossChannelAgreement,
    comparisons: SequentialModelSet,
    stress: StressCapacityQualification,
    policy: RollbackPolicy,
) -> RollbackRecommendation:
    """Apply non-compensable hard gates before soft degradation evidence."""

    trace: list[DecisionTraceItem] = []
    reasons: set[str] = set()

    if execution.hard_risk_breach_codes or stress.hard_blocking_reason_codes:
        reasons.update(execution.hard_risk_breach_codes)
        reasons.update(stress.hard_blocking_reason_codes)
        trace.append(
            DecisionTraceItem(
                rule_id="HARD_RISK_BREACH",
                triggered=True,
                reason_code="P9_LIVE_HARD_RISK_BREACH",
            )
        )
        reasons.add("P9_LIVE_HARD_RISK_BREACH")
        return _recommendation(LiveHealthState.QUARANTINE_RECOMMENDED, trace, reasons)

    if execution.observation_count < policy.minimum_live_observations:
        trace.append(
            DecisionTraceItem(
                rule_id="MINIMUM_SAMPLE",
                triggered=True,
                observed_value=float(execution.observation_count),
                threshold_value=float(policy.minimum_live_observations),
                reason_code="P9_LIVE_ROLLBACK_EVIDENCE_INCOMPLETE",
            )
        )
        reasons.add("P9_LIVE_ROLLBACK_EVIDENCE_INCOMPLETE")
        return _recommendation(LiveHealthState.INSUFFICIENT_LIVE_EVIDENCE, trace, reasons)

    alpha_decay = None
    if execution.realized_net_alpha is not None and execution.reference_net_alpha is not None:
        alpha_decay = execution.realized_net_alpha - execution.reference_net_alpha
    alpha_trigger = alpha_decay is not None and alpha_decay < policy.alpha_decay_threshold
    trace.append(
        DecisionTraceItem(
            rule_id="ALPHA_DECAY",
            triggered=alpha_trigger,
            observed_value=alpha_decay,
            threshold_value=policy.alpha_decay_threshold,
            reason_code="P9_LIVE_ALPHA_DECAY_MATERIAL" if alpha_trigger else None,
        )
    )
    if alpha_trigger:
        reasons.add("P9_LIVE_ALPHA_DECAY_MATERIAL")

    cost = execution.mean_cost_error_bps
    cost_rollback = cost is not None and cost >= policy.cost_error_rollback_bps
    cost_watch = cost is not None and cost >= policy.cost_error_watch_bps
    trace.append(
        DecisionTraceItem(
            rule_id="COST_MODEL_ERROR",
            triggered=cost_watch,
            observed_value=cost,
            threshold_value=policy.cost_error_watch_bps,
            reason_code="P9_LIVE_COST_MODEL_MISS" if cost_watch else None,
        )
    )
    if cost_watch:
        reasons.add("P9_LIVE_COST_MODEL_MISS")

    capacity = execution.capacity_ratio_to_approved
    capacity_rollback = capacity is not None and capacity < policy.severe_capacity_ratio
    capacity_watch = capacity is not None and capacity < policy.minimum_capacity_ratio
    trace.append(
        DecisionTraceItem(
            rule_id="CAPACITY_CONTRACTION",
            triggered=capacity_watch,
            observed_value=capacity,
            threshold_value=policy.minimum_capacity_ratio,
            reason_code="P9_LIVE_CAPACITY_CONTRACTION" if capacity_watch else None,
        )
    )
    if capacity_watch:
        reasons.add("P9_LIVE_CAPACITY_CONTRACTION")

    challenger_superior = any(
        item.state is ComparisonState.CHALLENGER_SUPERIOR for item in comparisons.comparisons
    )
    trace.append(
        DecisionTraceItem(
            rule_id="CHALLENGER_SUPERIORITY",
            triggered=challenger_superior,
            reason_code="P9_LIVE_CHALLENGER_SUPERIOR_EVIDENCE" if challenger_superior else None,
        )
    )
    if challenger_superior:
        reasons.add("P9_LIVE_CHALLENGER_SUPERIOR_EVIDENCE")

    trace.append(
        DecisionTraceItem(
            rule_id="CONFIRMED_DRIFT",
            triggered=drift.confirmed,
            observed_value=drift.agreement_ratio,
            reason_code="P9_LIVE_DRIFT_MATERIAL" if drift.confirmed else None,
        )
    )
    if drift.confirmed:
        reasons.add("P9_LIVE_DRIFT_MATERIAL")

    if cost_rollback or capacity_rollback or (alpha_trigger and drift.confirmed):
        state = LiveHealthState.ROLLBACK_RECOMMENDED
    elif alpha_trigger or drift.confirmed or challenger_superior:
        state = policy.confirmed_drift_action
    elif cost_watch or capacity_watch:
        state = LiveHealthState.WATCH
    else:
        state = LiveHealthState.HEALTHY
    return _recommendation(state, trace, reasons)


def _recommendation(
    state: LiveHealthState,
    trace: list[DecisionTraceItem],
    reasons: set[str],
) -> RollbackRecommendation:
    payload = {
        "state": state,
        "trace": [item.model_dump(mode="json") for item in trace],
        "reasons": sorted(reasons),
    }
    return RollbackRecommendation(
        state=state,
        decision_trace=tuple(trace),
        reason_codes=tuple(sorted(reasons)),
        result_sha256=payload_sha256(payload),
    )
