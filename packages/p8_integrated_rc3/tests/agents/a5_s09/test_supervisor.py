from copy import deepcopy
from decimal import Decimal

import pytest

from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.enums import RuntimeMode
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.invariant_monitor import run_invariant_monitor
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.models_control import SafetySupervisorRequest
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.models_invariants import InvariantMonitorRequest
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.models_shift import ShiftMonitorRequest
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.safety_supervisor import run_safety_supervisor
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.shift_monitor import run_shift_monitor


def _supervisor_request(normal_request, inv_payload=None, shift_value=None, exposure=None):
    inv_req = normal_request.invariant_request if inv_payload is None else InvariantMonitorRequest.model_validate(inv_payload)
    shift_req = normal_request.shift_request
    if shift_value is not None:
        observations = list(shift_req.observations)
        observations[0] = observations[0].model_copy(update={"value": shift_value})
        shift_req = shift_req.model_copy(update={"observations": tuple(observations)})
    return SafetySupervisorRequest(
        context=normal_request.context,
        shift_result=run_shift_monitor(shift_req),
        invariant_result=run_invariant_monitor(inv_req),
        exposure_state=normal_request.exposure_state if exposure is None else exposure,
        policy=normal_request.supervisor_policy,
    )


def test_normal_mode(normal_request):
    result = run_safety_supervisor(_supervisor_request(normal_request))
    assert result.selected_mode is RuntimeMode.NORMAL


def test_material_shift_holds_new_risk(normal_request):
    result = run_safety_supervisor(_supervisor_request(normal_request, shift_value=10.0))
    assert result.selected_mode is RuntimeMode.HOLD_NO_NEW_RISK


def test_partial_fill_prefers_hedge(normal_request):
    exposure = normal_request.exposure_state.model_copy(update={"has_unhedged_partial_fill": True})
    result = run_safety_supervisor(_supervisor_request(normal_request, exposure=exposure))
    assert result.selected_mode is RuntimeMode.HEDGE_ONLY


def test_partial_fill_falls_back_to_flatten(normal_request):
    exposure = normal_request.exposure_state.model_copy(update={"has_unhedged_partial_fill": True, "safe_hedge_available": False})
    result = run_safety_supervisor(_supervisor_request(normal_request, exposure=exposure))
    assert result.selected_mode is RuntimeMode.CONTROLLED_FLATTEN


def test_partial_fill_halts_when_no_safe_action(normal_request):
    exposure = normal_request.exposure_state.model_copy(update={"has_unhedged_partial_fill": True, "safe_hedge_available": False, "safe_flatten_available": False})
    result = run_safety_supervisor(_supervisor_request(normal_request, exposure=exposure))
    assert result.selected_mode is RuntimeMode.HALT


def test_expired_policy_restricts(normal_request):
    policy = normal_request.supervisor_policy.model_copy(update={"valid_until": normal_request.context.decision_time})
    request = _supervisor_request(normal_request).model_copy(update={"policy": policy})
    result = run_safety_supervisor(request)
    assert result.selected_mode is RuntimeMode.HOLD_NO_NEW_RISK


@pytest.mark.parametrize("mode,actions", [
    (RuntimeMode.NORMAL, {"OPEN", "CLOSE", "HEDGE", "CANCEL"}),
    (RuntimeMode.HOLD_NO_NEW_RISK, {"HOLD", "CANCEL"}),
    (RuntimeMode.HEDGE_ONLY, {"HEDGE", "CANCEL"}),
    (RuntimeMode.HALT, set()),
])
def test_allowed_actions(normal_request, mode, actions):
    exposure = normal_request.exposure_state.model_copy(update={"has_unhedged_partial_fill": mode in {RuntimeMode.HEDGE_ONLY, RuntimeMode.HALT}, "safe_hedge_available": mode is RuntimeMode.HEDGE_ONLY, "safe_flatten_available": False})
    request = _supervisor_request(normal_request, exposure=exposure)
    if mode is RuntimeMode.HOLD_NO_NEW_RISK:
        request = _supervisor_request(normal_request, shift_value=10.0)
    result = run_safety_supervisor(request)
    assert set(result.command.allowed_actions) == actions
