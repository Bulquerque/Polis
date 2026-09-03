from __future__ import annotations

from datetime import timedelta

from quant_pipeline.phase_08_portfolio_control.risk_state.contracts import (
    CandidateEconomicPackage, LinearLeg, LiquidityQuote, MarketLiquiditySnapshot,
)
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.liquidity import build_liquidity_state
from quant_pipeline.phase_08_portfolio_control.risk_state.ports import ExecutionRiskEstimate


class QualifiedExecutionEstimator:
    def estimate(self, candidate_id: str, capacity_units: float) -> ExecutionRiskEstimate:
        return ExecutionRiskEstimate(
            fill_probability=0.9, partial_fill_risk=0.1, legging_risk=0.05,
            impact_cost=1.0, quality_status="QUALIFIED",
        )


def test_haircut_monotonically_reduces_capacity(s4_request):
    base = build_liquidity_state(
        s4_request.candidates, s4_request.liquidity_snapshot, 0.0,
        s4_request.liquidity_policy,
    )
    reduced = build_liquidity_state(
        s4_request.candidates, s4_request.liquidity_snapshot, 0.5,
        s4_request.liquidity_policy,
    )
    for left, right in zip(base.states, reduced.states):
        assert right.capacity_units <= left.capacity_units


def test_stale_quote_is_unavailable(s4_request):
    stale = s4_request.liquidity_snapshot.quotes[0].model_copy(update={
        "quote_time": s4_request.decision_time - timedelta(hours=2),
    })
    snapshot = MarketLiquiditySnapshot(
        decision_time=s4_request.decision_time,
        quotes=(stale, s4_request.liquidity_snapshot.quotes[1]),
    )
    result = build_liquidity_state(
        s4_request.candidates, snapshot, 0.0, s4_request.liquidity_policy,
    )
    linear = next(item for item in result.states if item.candidate_id == "C-LINEAR")
    assert linear.fidelity.value == "UNAVAILABLE"
    assert any(code.startswith("QUOTE_STALE") for code in linear.reason_codes)


def test_multi_leg_capacity_uses_weakest_leg(s4_request, linear_candidate):
    second_leg = LinearLeg(
        leg_id="L-SECOND", instrument_id="INST-SECOND", factor_id="A",
        quantity_per_unit=2.0, pnl_per_factor_unit=100.0, currency="USD",
    )
    candidate = CandidateEconomicPackage(
        candidate_id="C-MULTI", canonical_candidate_id="CAN-MULTI",
        strategy_family="MULTI", currency="USD", unit_definition="one",
        gross_notional_per_unit=2_000, maximum_loss_per_unit=2_000,
        maximum_loss_proof_status="PROVEN",
        legs=(linear_candidate.legs[0], second_leg), source_ref=linear_candidate.source_ref,
    )
    quote = LiquidityQuote(
        instrument_id="INST-SECOND", bid=10, ask=10.1, bid_size=20, ask_size=20,
        daily_volume=100, open_interest=100, quote_time=s4_request.decision_time,
        available_at=s4_request.decision_time,
    )
    snapshot = MarketLiquiditySnapshot(
        decision_time=s4_request.decision_time,
        quotes=s4_request.liquidity_snapshot.quotes + (quote,),
    )
    result = build_liquidity_state((candidate,), snapshot, 0.0, s4_request.liquidity_policy)
    assert result.states[0].weakest_leg_id == "L-SECOND"


def test_qualified_port_removes_rule_based_degradation(s4_request):
    result = build_liquidity_state(
        s4_request.candidates, s4_request.liquidity_snapshot, 0.0,
        s4_request.liquidity_policy, QualifiedExecutionEstimator(),
    )
    assert all(item.fidelity.value == "FULLY_QUALIFIED" for item in result.states)
