from __future__ import annotations

import hashlib

from .enums import AlertSeverity, ReasonCode, RuntimeMode, ShiftState
from .models_control import (
    RuntimeControlCommand,
    SafetySupervisorRequest,
    SafetySupervisorResult,
)


def _command_id(request: SafetySupervisorRequest, mode: RuntimeMode) -> str:
    raw = f"{request.context.run_id}|{request.context.cycle_id}|{mode}|{request.context.observed_at.isoformat()}"
    return "rtc_" + hashlib.sha256(raw.encode()).hexdigest()[:20]


def _mode_for_partial_fill(request: SafetySupervisorRequest) -> RuntimeMode | None:
    exposure = request.exposure_state
    if not exposure.has_unhedged_partial_fill:
        return None
    if exposure.safe_hedge_available and exposure.market_access_available:
        return RuntimeMode.HEDGE_ONLY
    if exposure.safe_flatten_available and exposure.market_access_available:
        return RuntimeMode.CONTROLLED_FLATTEN
    return RuntimeMode.HALT


def _select_mode(request: SafetySupervisorRequest) -> tuple[RuntimeMode, list[ReasonCode]]:
    partial = _mode_for_partial_fill(request)
    if partial is not None:
        return partial, [ReasonCode.UNHEDGED_PARTIAL_FILL]
    severity = request.invariant_result.highest_severity
    reasons = [v.reason_code for v in request.invariant_result.violations]
    if severity is AlertSeverity.STATE_INCONSISTENT:
        return request.policy.state_inconsistent_mode, reasons
    if severity is AlertSeverity.CRITICAL:
        mode = request.policy.critical_margin_mode
        if mode is RuntimeMode.CONTROLLED_FLATTEN and not request.exposure_state.safe_flatten_available:
            return RuntimeMode.HALT, reasons + [ReasonCode.FALLBACK_NOT_FEASIBLE]
        return mode, reasons
    if severity is AlertSeverity.MATERIAL:
        return RuntimeMode.HOLD_NO_NEW_RISK, reasons
    shift = request.shift_result.overall_state
    if shift in {ShiftState.TAIL_SHIFT, ShiftState.LIQUIDITY_SHIFT, ShiftState.EXECUTION_MODEL_SHIFT, ShiftState.MATERIAL_SHIFT}:
        shift_reasons = [code for result in request.shift_result.metric_results for code in result.reason_codes]
        return request.policy.material_shift_mode, shift_reasons
    if shift is ShiftState.MONITOR_DEGRADED:
        return RuntimeMode.HOLD_NO_NEW_RISK, [ReasonCode.MONITOR_DATA_STALE]
    return RuntimeMode.NORMAL, []


def _allowed_actions(mode: RuntimeMode) -> tuple[str, ...]:
    mapping = {
        RuntimeMode.NORMAL: ("OPEN", "CLOSE", "HEDGE", "CANCEL"),
        RuntimeMode.HOLD_NO_NEW_RISK: ("HOLD", "CANCEL"),
        RuntimeMode.CANCEL_OPEN_ORDERS: ("CANCEL",),
        RuntimeMode.CLOSE_ONLY: ("CLOSE", "CANCEL"),
        RuntimeMode.RISK_REDUCTION_ONLY: ("REDUCE", "CLOSE", "CANCEL"),
        RuntimeMode.HEDGE_ONLY: ("HEDGE", "CANCEL"),
        RuntimeMode.CONTROLLED_FLATTEN: ("FLATTEN", "HEDGE", "CANCEL"),
        RuntimeMode.HALT: (),
    }
    return mapping[mode]


def _feasible(request: SafetySupervisorRequest, mode: RuntimeMode) -> bool:
    exposure = request.exposure_state
    if mode in {RuntimeMode.HEDGE_ONLY}:
        return exposure.safe_hedge_available and exposure.market_access_available
    if mode in {RuntimeMode.CONTROLLED_FLATTEN}:
        return exposure.safe_flatten_available and exposure.market_access_available
    if mode is RuntimeMode.CANCEL_OPEN_ORDERS:
        return exposure.safe_cancel_available
    return True


def run_safety_supervisor(request: SafetySupervisorRequest) -> SafetySupervisorResult:
    if request.policy.valid_until < request.context.observed_at:
        mode, reasons = RuntimeMode.HOLD_NO_NEW_RISK, [ReasonCode.RUNTIME_POLICY_EXPIRED]
    else:
        mode, reasons = _select_mode(request)
    feasible = _feasible(request, mode)
    if not feasible:
        mode = RuntimeMode.HALT
        reasons.append(ReasonCode.FALLBACK_NOT_FEASIBLE)
    command_id = _command_id(request, mode)
    command = RuntimeControlCommand(
        command_id=command_id,
        mode=mode,
        reason_codes=tuple(dict.fromkeys(reasons)),
        issued_at=request.context.observed_at,
        valid_until=request.policy.valid_until,
        idempotency_key=command_id,
        allowed_actions=_allowed_actions(mode),
        feasibility_proven=feasible,
    )
    return SafetySupervisorResult(
        selected_mode=mode,
        command=command,
        trigger_severity=request.invariant_result.highest_severity,
        trigger_shift_state=request.shift_result.overall_state,
    )
