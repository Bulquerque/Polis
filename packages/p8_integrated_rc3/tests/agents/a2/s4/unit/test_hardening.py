from __future__ import annotations

from datetime import timedelta
import json
import sys

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_08_portfolio_control.risk_state import cli
from quant_pipeline.phase_08_portfolio_control.risk_state.contracts import (
    ComponentQuality,
    GreekPolicy,
    GreekVector,
    LiquidityQuote,
    MarginFidelity,
    MarginPolicy,
    MarginRules,
    MarketLiquiditySnapshot,
)
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.greek_path import build_greek_path_state
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.margin_funding import build_margin_funding_state
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.pnl_cube import build_pnl_cube
from quant_pipeline.phase_08_portfolio_control.risk_state.ports import BrokerMarginEstimate


def _cube(request):
    return build_pnl_cube(
        request.scenario_artifacts,
        request.candidates,
        request.factor_definitions,
        request.step_year_fractions,
        request.pnl_policy,
    )[0]


def test_snapshot_rejects_quote_time_after_decision(now):
    quote = LiquidityQuote(
        instrument_id="X",
        bid=10.0,
        ask=11.0,
        bid_size=1.0,
        ask_size=1.0,
        quote_time=now + timedelta(seconds=1),
        available_at=now + timedelta(seconds=1),
    )
    with pytest.raises(ValidationError, match="future quote_time"):
        MarketLiquiditySnapshot(decision_time=now, quotes=(quote,))


def test_option_provided_greek_mismatch_degrades(s4_request, option_candidate):
    leg = option_candidate.legs[0].model_copy(
        update={"provided_greeks_per_unit": GreekVector(delta=999_999.0)}
    )
    option = option_candidate.model_copy(update={"legs": (leg,)})
    request = s4_request.model_copy(update={"candidates": (option,)})
    _, summary = build_greek_path_state(
        _cube(request),
        request.candidates,
        (),
        (),
        GreekPolicy(approximation_error_max=0.01),
        True,
    )
    assert summary.quality == ComponentQuality.DEGRADED
    assert "PROVIDED_GREEKS_MISMATCH_ANALYTIC" in summary.reason_codes


def test_concentration_addon_increases_exact_margin(s4_request):
    rules = MarginRules(
        fidelity=MarginFidelity.EXACT_BROKER_MODEL,
        exact_margin_per_candidate={"C-LINEAR": 1_000.0, "C-CALL": 800.0},
        concentration_threshold=0.01,
        concentration_addon_rate=0.20,
    )
    result = build_margin_funding_state(
        _cube(s4_request),
        s4_request.candidates,
        s4_request.account_state,
        s4_request.borrow_records,
        rules,
        0.0,
        s4_request.margin_policy,
    )
    linear = next(item for item in result.candidate_states if item.candidate_id == "C-LINEAR")
    assert linear.margin_per_unit == pytest.approx(1_200.0)
    assert "CONCENTRATION_ADDON_APPLIED" in linear.reason_codes


def test_exact_margin_missing_candidate_is_unavailable(s4_request):
    rules = MarginRules(
        fidelity=MarginFidelity.EXACT_BROKER_MODEL,
        exact_margin_per_candidate={"OTHER": 10.0},
    )
    result = build_margin_funding_state(
        _cube(s4_request),
        s4_request.candidates,
        s4_request.account_state,
        s4_request.borrow_records,
        rules,
        0.0,
        s4_request.margin_policy,
    )
    assert all(item.quality == ComponentQuality.UNAVAILABLE for item in result.candidate_states)
    assert all("MARGIN_MODEL_UNAVAILABLE" in item.reason_codes for item in result.candidate_states)


def test_disabled_margin_fallback_is_unavailable(s4_request):
    result = build_margin_funding_state(
        _cube(s4_request),
        s4_request.candidates,
        s4_request.account_state,
        s4_request.borrow_records,
        MarginRules(fidelity=MarginFidelity.CONSERVATIVE_RULE_BASED),
        0.0,
        MarginPolicy(allow_span_like=False, allow_rule_based=False),
    )
    assert all(item.margin_per_unit is None for item in result.candidate_states)
    assert all(item.quality == ComponentQuality.UNAVAILABLE for item in result.candidate_states)


class DegradedBrokerMargin:
    def estimate_margin(self, candidate_id: str) -> BrokerMarginEstimate:
        return BrokerMarginEstimate(
            candidate_id=candidate_id,
            margin_per_unit=100.0,
            quality_status="DEGRADED",
            reason_codes=("BROKER_ESTIMATE_DEGRADED",),
        )


def test_broker_degraded_status_is_preserved(s4_request):
    result = build_margin_funding_state(
        _cube(s4_request),
        s4_request.candidates,
        s4_request.account_state,
        s4_request.borrow_records,
        MarginRules(
            fidelity=MarginFidelity.EXACT_BROKER_MODEL,
            exact_margin_per_candidate={"placeholder": 1.0},
        ),
        0.0,
        s4_request.margin_policy,
        DegradedBrokerMargin(),
    )
    assert all(item.quality == ComponentQuality.DEGRADED for item in result.candidate_states)
    assert all("BROKER_ESTIMATE_DEGRADED" in item.reason_codes for item in result.candidate_states)


def test_cli_main_direct(s4_request, tmp_path, monkeypatch, capsys):
    request_file = tmp_path / "request.json"
    output_dir = tmp_path / "out"
    request_file.write_text(
        json.dumps(s4_request.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["p8-s4-run", str(request_file), str(output_dir)])
    assert cli.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["cycle_id"] == s4_request.cycle_id
    assert (output_dir / "s4_result.json").exists()
