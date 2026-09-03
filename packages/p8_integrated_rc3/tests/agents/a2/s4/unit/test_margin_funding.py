from __future__ import annotations

from quant_pipeline.phase_08_portfolio_control.risk_state.contracts import (
    BorrowRecord, ComponentQuality, MarginFidelity, MarginRules,
)
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.margin_funding import build_margin_funding_state
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.pnl_cube import build_pnl_cube
from quant_pipeline.phase_08_portfolio_control.risk_state.ports import BrokerMarginEstimate


class QualifiedBrokerMargin:
    def estimate_margin(self, candidate_id: str) -> BrokerMarginEstimate:
        return BrokerMarginEstimate(
            candidate_id=candidate_id,
            margin_per_unit=1_000.0 if candidate_id == "C-LINEAR" else 600.0,
            quality_status="QUALIFIED",
        )


def _cube(request):
    return build_pnl_cube(
        request.scenario_artifacts, request.candidates, request.factor_definitions,
        request.step_year_fractions, request.pnl_policy,
    )[0]


def test_span_like_margin_is_explicitly_degraded(s4_request):
    result = build_margin_funding_state(
        _cube(s4_request), s4_request.candidates, s4_request.account_state,
        s4_request.borrow_records, s4_request.margin_rules,
        s4_request.s3_result.ambiguity.margin_buffer, s4_request.margin_policy,
    )
    assert all(state.fidelity == MarginFidelity.SPAN_LIKE_MODEL for state in result.candidate_states)
    assert all(state.quality == ComponentQuality.DEGRADED for state in result.candidate_states)
    assert all(state.margin_per_unit >= 0 for state in result.candidate_states)


def test_exact_broker_port_qualifies_margin(s4_request):
    result = build_margin_funding_state(
        _cube(s4_request), s4_request.candidates, s4_request.account_state,
        s4_request.borrow_records,
        MarginRules(
            fidelity=MarginFidelity.EXACT_BROKER_MODEL,
            exact_margin_per_candidate={"placeholder": 1.0},
        ),
        0.0, s4_request.margin_policy, QualifiedBrokerMargin(),
    )
    assert all(state.fidelity == MarginFidelity.EXACT_BROKER_MODEL for state in result.candidate_states)
    assert all(state.quality == ComponentQuality.FULLY_QUALIFIED for state in result.candidate_states)


def test_borrow_unavailable_blocks_short_candidate(s4_request, linear_candidate):
    short_leg = linear_candidate.legs[0].model_copy(update={"quantity_per_unit": -1.0})
    short_candidate = linear_candidate.model_copy(update={
        "candidate_id": "C-SHORT", "canonical_candidate_id": "CAN-SHORT",
        "legs": (short_leg,),
    })
    request = s4_request.model_copy(update={"candidates": (short_candidate,)})
    cube = build_pnl_cube(
        request.scenario_artifacts, request.candidates, request.factor_definitions,
        request.step_year_fractions, request.pnl_policy,
    )[0]
    result = build_margin_funding_state(
        cube, request.candidates, request.account_state,
        (BorrowRecord(instrument_id="INST-LINEAR", available=False),),
        request.margin_rules, 0.0, request.margin_policy,
    )
    state = result.candidate_states[0]
    assert state.borrow_available is False
    assert state.capital_capacity_units == 0.0
    assert state.quality == ComponentQuality.UNAVAILABLE


def test_rule_based_margin_requires_real_notional(s4_request, linear_candidate):
    candidate = linear_candidate.model_copy(update={
        "gross_notional_per_unit": None,
        "maximum_loss_per_unit": None,
        "maximum_loss_proof_status": "UNAVAILABLE",
    })
    request = s4_request.model_copy(update={
        "candidates": (candidate,),
        "margin_rules": MarginRules(fidelity=MarginFidelity.CONSERVATIVE_RULE_BASED),
    })
    cube = build_pnl_cube(
        request.scenario_artifacts, request.candidates, request.factor_definitions,
        request.step_year_fractions, request.pnl_policy,
    )[0]
    result = build_margin_funding_state(
        cube, request.candidates, request.account_state,
        request.borrow_records, request.margin_rules, 0.0, request.margin_policy,
    )
    assert result.candidate_states[0].margin_per_unit is None
    assert result.candidate_states[0].quality == ComponentQuality.UNAVAILABLE
