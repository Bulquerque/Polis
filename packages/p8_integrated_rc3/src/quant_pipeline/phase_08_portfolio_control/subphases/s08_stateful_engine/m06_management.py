from __future__ import annotations

from quant_pipeline.phase_08_portfolio_control.foundation.enums import OrderStatus, RuntimeControlMode
from quant_pipeline.phase_08_portfolio_control.foundation.hashing import content_sha256, deterministic_id
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import RuntimeControlCommand

from .enums import ManagementActionType, ManagementSignalType, ValuationStatus
from .input_models import S8InputBundle
from .management_models import ManagementAction, ManagementDecisionBundle, ReoptimizationRequest
from .state_models import AccountingBundle, ExecutionStateBundle, PositionLifecycleBundle
from .valuation_models import ValuationBundle

MODULE_ID = "P8.S8.M06"


_MODE_ACTION = {
    RuntimeControlMode.CANCEL_OPEN_ORDERS: ManagementActionType.CANCEL_OPEN_ORDERS,
    RuntimeControlMode.CLOSE_ONLY: ManagementActionType.CLOSE_ONLY,
    RuntimeControlMode.RISK_REDUCTION_ONLY: ManagementActionType.RISK_REDUCTION_ONLY,
    RuntimeControlMode.HEDGE_ONLY: ManagementActionType.HEDGE_ONLY,
    RuntimeControlMode.CONTROLLED_FLATTEN: ManagementActionType.CONTROLLED_FLATTEN,
    RuntimeControlMode.HALT: ManagementActionType.HALT,
    RuntimeControlMode.HOLD_NO_NEW_RISK: ManagementActionType.HOLD,
}


def _active_mode(value: S8InputBundle) -> RuntimeControlMode:
    commands = [item for item in value.runtime_commands if isinstance(item, RuntimeControlCommand)]
    if not commands:
        return RuntimeControlMode.NORMAL
    return max(commands, key=lambda item: (item.command_sequence, item.event_time, item.command_id)).mode


def _action(value, action_type, reason, instruments=(), candidates=(), authorization=False):
    return ManagementAction(
        action_id=deterministic_id("management-action",value.cycle_id,action_type,reason,value.valuation_time),
        event_time=value.valuation_time, action_type=action_type, reason_code=reason,
        requires_new_authorization=authorization,
        affected_instrument_ids=tuple(sorted(set(instruments))),
        affected_candidate_ids=tuple(sorted(set(candidates))),
    )


def _request(value, reason, state_hash, instruments=(), candidates=()):
    next_cycle=deterministic_id("cycle",value.cycle_id,reason,value.valuation_time)
    return ReoptimizationRequest(
        request_id=deterministic_id("reopt",value.cycle_id,reason,state_hash),
        event_time=value.valuation_time, source_cycle_id=value.cycle_id,
        requested_next_cycle_id=next_cycle, reason_code=reason, source_state_hash=state_hash,
        affected_instrument_ids=tuple(sorted(set(instruments))),
        affected_candidate_ids=tuple(sorted(set(candidates))),
    )


def execute(
    value: S8InputBundle,
    execution: ExecutionStateBundle,
    positions: PositionLifecycleBundle,
    accounting: AccountingBundle,
    valuation: ValuationBundle,
) -> ManagementDecisionBundle:
    state_hash=content_sha256({"execution":execution,"positions":positions,"accounting":accounting,"valuation":valuation})
    mode=_active_mode(value); actions=[]; requests=[]
    if mode != RuntimeControlMode.NORMAL:
        actions.append(_action(value,_MODE_ACTION[mode],f"RUNTIME_{mode.value}"))
    partial=[item.order_id for item in execution.orders if item.status==OrderStatus.PARTIALLY_FILLED]
    if partial and value.policies.management.auto_reoptimization_on_partial_fill:
        requests.append(_request(value,"PARTIAL_FILL",state_hash))
    if value.valuation_time >= value.s7_handoff.authorization_bundle.valid_until and value.policies.management.auto_reoptimization_on_target_expiry:
        requests.append(_request(value,"TARGET_EXPIRED",state_hash))
    for signal in value.management_signals:
        if signal.signal_type in {ManagementSignalType.TARGET_INVALIDATED,ManagementSignalType.PARTIAL_FILL,ManagementSignalType.LIFECYCLE_DUE,ManagementSignalType.RISK_REDUCTION_REQUIRED}:
            requests.append(_request(value,signal.reason_code,state_hash,signal.affected_instrument_ids,signal.affected_candidate_ids))
    if valuation.nav.status==ValuationStatus.INCOMPLETE and value.policies.management.hold_on_incomplete_valuation:
        actions.append(_action(value,ManagementActionType.HOLD,"VALUATION_INCOMPLETE"))
    if not actions and not requests:
        actions.append(_action(value,ManagementActionType.HOLD,"NO_MANAGEMENT_ACTION_REQUIRED"))
    if requests:
        actions.append(_action(value,ManagementActionType.REQUEST_REOPTIMIZATION,"REOPTIMIZATION_REQUIRED",authorization=True))
    # deterministic de-duplication
    actions=sorted({item.action_id:item for item in actions}.values(),key=lambda x:x.action_id)
    requests=sorted({item.request_id:item for item in requests}.values(),key=lambda x:x.request_id)
    payload={"actions":tuple(actions),"reoptimization_requests":tuple(requests),"active_runtime_mode":mode}
    return ManagementDecisionBundle(**payload,content_sha256=content_sha256(payload))
