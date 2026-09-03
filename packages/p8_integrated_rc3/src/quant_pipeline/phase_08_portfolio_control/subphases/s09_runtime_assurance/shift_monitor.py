from __future__ import annotations

from datetime import datetime

from .enums import MetricFamily, ReasonCode, ShiftState
from .models_shift import (
    MetricMonitorState,
    MetricObservation,
    MetricShiftResult,
    ShiftMonitorRequest,
    ShiftMonitorResult,
)


def _state_map(request: ShiftMonitorRequest) -> dict[str, MetricMonitorState]:
    states = {item.metric_name: item for item in request.prior_states}
    if len(states) != len(request.prior_states):
        raise ValueError("prior_states contains duplicate metric_name")
    return states


def _metric_state(family: MetricFamily, score: float, ready: bool) -> ShiftState:
    if not ready:
        return ShiftState.MONITOR_DEGRADED
    if score < 1.0:
        return ShiftState.IN_DISTRIBUTION
    if score < 2.0:
        return ShiftState.MILD_SHIFT
    if family is MetricFamily.RISK:
        return ShiftState.TAIL_SHIFT
    if family is MetricFamily.LIQUIDITY:
        return ShiftState.LIQUIDITY_SHIFT
    if family is MetricFamily.EXECUTION:
        return ShiftState.EXECUTION_MODEL_SHIFT
    return ShiftState.MATERIAL_SHIFT


def _reason(state: ShiftState) -> tuple[ReasonCode, ...]:
    mapping = {
        ShiftState.TAIL_SHIFT: ReasonCode.TAIL_RISK_SHIFT,
        ShiftState.LIQUIDITY_SHIFT: ReasonCode.LIQUIDITY_DETERIORATION,
        ShiftState.EXECUTION_MODEL_SHIFT: ReasonCode.EXECUTION_MODEL_DETERIORATION,
        ShiftState.MATERIAL_SHIFT: ReasonCode.MATERIAL_DISTRIBUTION_SHIFT,
        ShiftState.MONITOR_DEGRADED: ReasonCode.MONITOR_DATA_STALE,
    }
    code = mapping.get(state)
    return () if code is None else (code,)


def _update_one(
    observation: MetricObservation,
    prior: MetricMonitorState | None,
    request: ShiftMonitorRequest,
) -> tuple[MetricShiftResult, MetricMonitorState]:
    policy = request.policy
    previous = prior or MetricMonitorState(metric_name=observation.metric_name, count=0)
    if previous.last_observed_at is not None and observation.observed_at <= previous.last_observed_at:
        raise ValueError("observations must advance metric time")
    age = (request.context.observed_at - observation.observed_at).total_seconds()
    z_score = (observation.value - observation.baseline_mean) / observation.baseline_std
    ewma = policy.alpha * z_score + (1.0 - policy.alpha) * previous.ewma_z
    positive = max(0.0, previous.cusum_positive + z_score - policy.drift_allowance)
    negative = max(0.0, previous.cusum_negative - z_score - policy.drift_allowance)
    raw = max(abs(ewma), positive, negative)
    scaled = _scaled_score(raw, policy.mild_threshold, policy.material_threshold)
    ready = previous.count + 1 >= policy.minimum_observations and age <= policy.maximum_observation_age_seconds
    state = _metric_state(observation.family, scaled, ready)
    next_state = MetricMonitorState(
        metric_name=observation.metric_name,
        count=previous.count + 1,
        ewma_z=ewma,
        cusum_positive=positive,
        cusum_negative=negative,
        last_observed_at=observation.observed_at,
    )
    result = MetricShiftResult(
        metric_name=observation.metric_name,
        family=observation.family,
        z_score=z_score,
        ewma_z=ewma,
        cusum_score=max(positive, negative),
        state=state,
        reason_codes=_reason(state),
    )
    return result, next_state


def _scaled_score(raw: float, mild: float, material: float) -> float:
    if raw < mild:
        return raw / mild
    if raw < material:
        return 1.0 + (raw - mild) / (material - mild)
    return 2.0 + (raw - material) / max(material, 1e-12)


def _overall(results: tuple[MetricShiftResult, ...]) -> ShiftState:
    priority = [
        ShiftState.MONITOR_DEGRADED,
        ShiftState.TAIL_SHIFT,
        ShiftState.LIQUIDITY_SHIFT,
        ShiftState.EXECUTION_MODEL_SHIFT,
        ShiftState.MATERIAL_SHIFT,
        ShiftState.MILD_SHIFT,
        ShiftState.IN_DISTRIBUTION,
    ]
    states = {item.state for item in results}
    return next(state for state in priority if state in states)


def run_shift_monitor(request: ShiftMonitorRequest) -> ShiftMonitorResult:
    prior = _state_map(request)
    results: list[MetricShiftResult] = []
    next_states: list[MetricMonitorState] = []
    names: set[str] = set()
    for observation in request.observations:
        if observation.metric_name in names:
            raise ValueError("observations contains duplicate metric_name")
        names.add(observation.metric_name)
        result, state = _update_one(observation, prior.get(observation.metric_name), request)
        results.append(result)
        next_states.append(state)
    ordered_results = tuple(sorted(results, key=lambda item: item.metric_name))
    ordered_states = tuple(sorted(next_states, key=lambda item: item.metric_name))
    return ShiftMonitorResult(
        overall_state=_overall(ordered_results),
        metric_results=ordered_results,
        next_states=ordered_states,
        generated_at=request.context.observed_at,
    )
