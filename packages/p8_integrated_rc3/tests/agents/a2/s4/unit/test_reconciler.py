from __future__ import annotations

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import (
    ActionabilityState,
)
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.dependence import build_dependence
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.greek_path import build_greek_path_state
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.liquidity import build_liquidity_state
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.margin_funding import build_margin_funding_state
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.pnl_cube import build_pnl_cube
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.reconciler import reconcile_risk_state


def _components(request):
    cube, quality = build_pnl_cube(
        request.scenario_artifacts, request.candidates, request.factor_definitions,
        request.step_year_fractions, request.pnl_policy,
    )
    _, dependence = build_dependence(cube, request.dependence_policy)
    _, greek = build_greek_path_state(
        cube, request.candidates, (), (), request.greek_policy, True,
    )
    liquidity = build_liquidity_state(
        request.candidates, request.liquidity_snapshot,
        request.s3_result.ambiguity.liquidity_haircut, request.liquidity_policy,
    )
    margin = build_margin_funding_state(
        cube, request.candidates, request.account_state, request.borrow_records,
        request.margin_rules, request.s3_result.ambiguity.margin_buffer,
        request.margin_policy,
    )
    return cube, quality, dependence, greek, liquidity, margin


def test_degraded_components_produce_degraded_sizability(s4_request):
    cube, quality, dependence, greek, liquidity, margin = _components(s4_request)
    states, receipt = reconcile_risk_state(
        s4_request.candidates, cube, quality, dependence, greek, liquidity, margin,
        s4_request.s3_result, s4_request.reconciliation_policy.degraded_cap_multiplier,
    )
    assert all(state.state.value in {"DEGRADED_SIZABLE", "NOT_SIZABLE"} for state in states)
    assert set(receipt.candidate_status) == {"C-LINEAR", "C-CALL"}


def test_no_new_risk_actionability_blocks_all_candidates(s4_request):
    cube, quality, dependence, greek, liquidity, margin = _components(s4_request)
    ambiguity = s4_request.s3_result.ambiguity.model_copy(update={
        "actionability_state": ActionabilityState.NO_NEW_RISK,
        "risk_budget_cap": 0.0,
    })
    s3_result = s4_request.s3_result.model_copy(update={"ambiguity": ambiguity})
    states, _ = reconcile_risk_state(
        s4_request.candidates, cube, quality, dependence, greek, liquidity, margin,
        s3_result, s4_request.reconciliation_policy.degraded_cap_multiplier,
    )
    assert all(state.state.value == "NOT_SIZABLE" for state in states)
    assert all(state.max_units == 0.0 for state in states)
