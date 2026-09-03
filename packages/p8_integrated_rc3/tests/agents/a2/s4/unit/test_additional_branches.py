from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.arrays import ScenarioSet
from quant_pipeline.phase_08_portfolio_control.risk_state.contracts import (
    ComponentQuality,
    DependencePolicy,
    FactorDefinition,
    LiquidityQuote,
    MarginFidelity,
    MarginOffsetRule,
    MarginRules,
    MarketLiquiditySnapshot,
    OptionType,
    ShockKind,
)
from quant_pipeline.phase_08_portfolio_control.risk_state.errors import ValuationCapabilityError
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.dependence import build_dependence
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.liquidity import build_liquidity_state
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.margin_funding import build_margin_funding_state
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.pnl_cube import build_pnl_cube
from quant_pipeline.phase_08_portfolio_control.risk_state.ports import ExecutionRiskEstimate


class DegradedExecutionEstimator:
    def estimate(self, candidate_id: str, capacity_units: float) -> ExecutionRiskEstimate:
        return ExecutionRiskEstimate(
            fill_probability=0.01,
            partial_fill_risk=0.99,
            legging_risk=0.99,
            impact_cost=10.0,
            quality_status="DEGRADED",
            reason_codes=("MODEL_UNQUALIFIED",),
        )


def test_put_option_without_vol_or_rate_factors(s4_request, option_candidate):
    leg = option_candidate.legs[0].model_copy(update={
        "option_type": OptionType.PUT,
        "volatility_factor_id": None,
        "rate_factor_id": None,
    })
    candidate = option_candidate.model_copy(update={
        "candidate_id": "C-PUT", "canonical_candidate_id": "CAN-PUT", "legs": (leg,),
    })
    cube, quality = build_pnl_cube(
        s4_request.scenario_artifacts, (candidate,), s4_request.factor_definitions,
        s4_request.step_year_fractions, s4_request.pnl_policy,
    )
    assert cube.candidate_pnl.shape[2] == 1
    assert quality["C-PUT"].value == "FULL_REPRICING"


def test_missing_factor_is_explicit_capability_error(s4_request, linear_candidate):
    leg = linear_candidate.legs[0].model_copy(update={"factor_id": "MISSING"})
    candidate = linear_candidate.model_copy(update={"legs": (leg,)})
    with pytest.raises(ValuationCapabilityError):
        build_pnl_cube(
            s4_request.scenario_artifacts, (candidate,), s4_request.factor_definitions,
            s4_request.step_year_fractions, s4_request.pnl_policy,
        )


def test_simple_return_below_minus_one_is_rejected(s4_request, tmp_path):
    root = Path(s4_request.scenario_artifacts.root_path)
    source = ScenarioSet.load_npz(root / s4_request.scenario_artifacts.reduced_scenarios_file)
    values = source.values.copy()
    values[0, 0, source.factor_ids.index("B")] = -1.1
    changed = ScenarioSet(
        values=values, probabilities=source.probabilities, scenario_ids=source.scenario_ids,
        factor_ids=source.factor_ids, step_labels=source.step_labels, origins=source.origins,
    )
    target_root = tmp_path / "bad-return"
    target_root.mkdir()
    changed.save_npz(target_root / "reduced.npz")
    (root / s4_request.scenario_artifacts.full_scenarios_file).replace(target_root / "full.npz")
    (root / s4_request.scenario_artifacts.stress_scenarios_file).replace(target_root / "stress.npz")
    bundle = s4_request.scenario_artifacts.model_copy(update={
        "root_path": str(target_root),
        "reduced_scenarios_file": "reduced.npz",
        "full_scenarios_file": "full.npz",
        "stress_scenarios_file": "stress.npz",
        "reduced_scenarios_sha256": changed.content_sha256(),
    })
    with pytest.raises(ValuationCapabilityError):
        build_pnl_cube(
            bundle, s4_request.candidates, s4_request.factor_definitions,
            s4_request.step_year_fractions, s4_request.pnl_policy,
        )


def test_explicit_shrinkage_and_excessive_repair_degrade(s4_request):
    cube, _ = build_pnl_cube(
        s4_request.scenario_artifacts, s4_request.candidates,
        s4_request.factor_definitions, s4_request.step_year_fractions, s4_request.pnl_policy,
    )
    policy = DependencePolicy(
        shrinkage_alpha=0.5, max_psd_repair_relative=0.0,
        minimum_effective_samples=2,
    )
    _, summary = build_dependence(cube, policy)
    assert summary.shrinkage_alpha == 0.5
    assert summary.quality in {ComponentQuality.FULLY_QUALIFIED, ComponentQuality.DEGRADED}


def test_missing_quote_and_low_fill_are_unavailable(s4_request):
    snapshot = MarketLiquiditySnapshot(
        decision_time=s4_request.decision_time,
        quotes=(s4_request.liquidity_snapshot.quotes[0],),
    )
    result = build_liquidity_state(
        s4_request.candidates, snapshot, 0.0, s4_request.liquidity_policy,
        DegradedExecutionEstimator(),
    )
    call = next(state for state in result.states if state.candidate_id == "C-CALL")
    assert call.fidelity == ComponentQuality.UNAVAILABLE
    linear = next(state for state in result.states if state.candidate_id == "C-LINEAR")
    assert linear.fidelity == ComponentQuality.UNAVAILABLE
    assert "FILL_PROBABILITY_BELOW_FLOOR" in linear.reason_codes


def test_quote_contract_validation(now):
    with pytest.raises(ValidationError):
        LiquidityQuote(
            instrument_id="X", bid=11, ask=10, bid_size=1, ask_size=1,
            quote_time=now, available_at=now,
        )
    with pytest.raises(ValidationError):
        LiquidityQuote(
            instrument_id="X", bid=10, ask=11, bid_size=1, ask_size=1,
            quote_time=now + timedelta(seconds=1), available_at=now,
        )


def test_exact_margin_offsets_and_portfolio_value(s4_request):
    rules = MarginRules(
        fidelity=MarginFidelity.EXACT_BROKER_MODEL,
        exact_margin_per_candidate={"C-LINEAR": 1_000.0, "C-CALL": 800.0},
        exact_portfolio_margin=4_500.0,
        recognized_offsets=(MarginOffsetRule(group_id="G", offset_fraction=0.25),),
    )
    candidates = (
        s4_request.candidates[0].model_copy(update={"margin_offset_group": "G"}),
        s4_request.candidates[1],
    )
    request = s4_request.model_copy(update={"candidates": candidates})
    cube, _ = build_pnl_cube(
        request.scenario_artifacts, request.candidates, request.factor_definitions,
        request.step_year_fractions, request.pnl_policy,
    )
    result = build_margin_funding_state(
        cube, candidates, request.account_state, request.borrow_records,
        rules, 0.0, request.margin_policy,
    )
    assert result.portfolio_margin_current == 4_500.0
    linear = next(x for x in result.candidate_states if x.candidate_id == "C-LINEAR")
    assert linear.margin_per_unit == 750.0


def test_margin_rules_exact_requires_values():
    with pytest.raises(ValidationError):
        MarginRules(fidelity=MarginFidelity.EXACT_BROKER_MODEL)


def test_absolute_factor_definition_can_value_option(s4_request, option_candidate):
    definitions = tuple(
        FactorDefinition(factor_id=x.factor_id, shock_kind=(ShockKind.ABSOLUTE if x.factor_id == "A" else x.shock_kind), unit=x.unit)
        for x in s4_request.factor_definitions
    )
    cube, _ = build_pnl_cube(
        s4_request.scenario_artifacts, (option_candidate,), definitions,
        s4_request.step_year_fractions, s4_request.pnl_policy,
    )
    assert np.all(np.isfinite(cube.candidate_pnl))
