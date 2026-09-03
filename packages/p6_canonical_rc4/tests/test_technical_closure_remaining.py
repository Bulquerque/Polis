from __future__ import annotations

import json
import runpy
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from conftest import DECISION_TIME, build_configuration, build_inputs
from test_technical_closure_branches import advanced_config, advanced_result, records
from quant_pipeline.phase_06_strategy_synthesis import cli
from quant_pipeline.phase_06_strategy_synthesis.boundaries import p5
from quant_pipeline.phase_06_strategy_synthesis.domain.enums import (
    CalculationStatus, InstrumentType, MutationOperator, OptionType, Side,
    TargetPayoffMode,
)
from quant_pipeline.phase_06_strategy_synthesis.domain.models import (
    InstrumentReference, StrategyLeg, TargetPayoff,
)
from quant_pipeline.phase_06_strategy_synthesis.foundation.errors import Phase6Error
from quant_pipeline.phase_06_strategy_synthesis.foundation.hashing import canonical_sha256
from quant_pipeline.phase_06_strategy_synthesis.subphase_01_boundary_market_snapshot import services as s1
from quant_pipeline.phase_06_strategy_synthesis.subphase_02_canonical_strategy_domain.services import _contract_rejection_reason
from quant_pipeline.phase_06_strategy_synthesis.subphase_03_template_generation import family_generators, generation, planning
from quant_pipeline.phase_06_strategy_synthesis.subphase_04_mutation_deformation import mutation_engine, mutation_operators
from quant_pipeline.phase_06_strategy_synthesis.subphase_04_mutation_deformation import validation as mutation_validation
from quant_pipeline.phase_06_strategy_synthesis.subphase_05_target_payoff import market_implied, target_builder
from quant_pipeline.phase_06_strategy_synthesis.subphase_06_inverse_design import basis, orchestrator, solver_common, solver_exact, solver_search
from quant_pipeline.phase_06_strategy_synthesis.subphase_07_pricing_scenario_evaluation import pathwise, services as s7
from quant_pipeline.phase_06_strategy_synthesis.subphase_08_feasibility_defined_risk import qualification_gates
from quant_pipeline.phase_06_strategy_synthesis.subphase_09_canonicalization_diversity import archive, canonicalization

D = Decimal


@pytest.mark.filterwarnings("ignore:.*found in sys.modules.*:RuntimeWarning")
def test_cli_main_and_module_entrypoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inputs = tmp_path / "inputs.json"
    config = tmp_path / "config.json"
    output = tmp_path / "output.json"
    inputs.write_text(json.dumps(build_inputs()), encoding="utf-8")
    config.write_text(json.dumps(build_configuration()), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["p6", "--inputs", str(inputs), "--configuration", str(config), "--output", str(output)])
    assert cli.main() == 0
    assert json.loads(output.read_text())["outputs"]
    output2 = tmp_path / "output2.json"
    monkeypatch.setattr(sys, "argv", ["p6", "--inputs", str(inputs), "--configuration", str(config), "--output", str(output2)])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("quant_pipeline.phase_06_strategy_synthesis.cli", run_name="__main__")
    assert exc.value.code == 0 and output2.exists()


def test_small_model_error_and_normalization_branches():
    base = records("validated_underlying_panel")[0]
    instrument = InstrumentReference(
        instrument_id="I", instrument_type=InstrumentType.UNDERLYING,
        underlying_id="XYZ", currency="USD", exchange="X", multiplier=D("1"),
        valid_from=DECISION_TIME, valid_until=None,
        source_artifact_id="a", source_record_id="r",
    )
    assert instrument.valid_until is None
    target = TargetPayoff(
        target_payoff_id="t", underlying_id="XYZ", decision_time=DECISION_TIME,
        horizon_days=1, objective_family=records("raw_strategy_candidate_panel")[0].objective_family,
        terminal_state_grid=(D("1"),), desired_payoff=(D("0"),),
        belief_state_id="b",
    )
    assert target.decision_time == DECISION_TIME
    leg = records("raw_strategy_candidate_panel")[0].legs[0]
    with pytest.raises(ValidationError):
        StrategyLeg.model_validate({**leg.model_dump(), "strike": None})
    err = Phase6Error("bad", "R", "M", {"x": 1})
    assert "reason_code=R" in str(err)
    invalid = base.model_copy(update={"last": None, "ask": None, "bid": None})
    assert invalid.last is None


def test_p5_underlying_fallback_and_boundary_loop_branches():
    payload = {"artifact_id": "v1", "records": [{
        "underlying": None, "underlying_id": "XYZ",
        "available_at": DECISION_TIME.isoformat(), "horizon_days": 2,
        "confidence": "0.5",
    }]}
    parsed = p5.parse_p5_beliefs({"underlying_forecast_panel": payload}, DECISION_TIME, "M")
    assert parsed[0].underlying_id == "XYZ"

    observation = records("validated_underlying_panel")[0]
    empty_observation = observation.model_copy(update={"last": None, "ask": None, "bid": None})
    assert s1._observed_price(empty_observation) is None
    contract = records("validated_option_contract_panel")[0]
    quote = records("validated_option_quote_panel")[0]
    no_price = quote.model_copy(update={"bid": None, "ask": None, "last": None})
    assert s1.static_arbitrage_diagnostics((contract,), (no_price,), (observation,)) == ()
    assert s1.static_arbitrage_diagnostics((contract,), (quote,), (empty_observation,)) == ()
    same = tuple(contract.model_copy(update={"contract_id": f"same-{i}", "strike": D("100")}) for i in range(3))
    same_quotes = tuple(quote.model_copy(update={"contract_id": item.contract_id}) for item in same)
    s1.static_arbitrage_diagnostics(same, same_quotes, (observation,))


def test_contract_template_planning_and_generation_branches():
    config = advanced_config("TEMPLATE_ONLY")
    contract = records("validated_option_contract_panel")[0]
    quote = records("validated_option_quote_panel")[0]
    unsupported = contract.model_copy(update={"settlement_type": "UNSUPPORTED"})
    assert _contract_rejection_reason(unsupported, quote, config) == "P6_SETTLEMENT_UNSUPPORTED"

    contracts = records("eligible_option_contract_panel")
    quotes = records("eligible_option_quote_panel")
    underlyings = records("validated_underlying_panel")
    plan = planning.TemplatePlan(contracts, quotes, underlyings, records("validated_market_belief_state"), config)
    calls = plan.contracts("XYZ", OptionType.CALL)
    puts = plan.contracts("XYZ", OptionType.PUT)
    captured = []
    family_generators.generate_volatility(plan, "XYZ", calls, puts, config, lambda *x: captured.append(x))
    assert captured
    no_short_put = config.model_copy(update={"strategy": config.strategy.model_copy(update={"allow_cash_secured_short_put": False})})
    captured.clear()
    family_generators.generate_skew(plan, "XYZ", calls, puts, no_short_put, lambda *x: captured.append(x))
    assert captured

    disabled = config.model_copy(update={"strategy": config.strategy.model_copy(update={"enabled_templates": ()})})
    assert generation._generate_for_underlying("volatility", plan, "XYZ", disabled) == []
    one_leg = config.model_copy(update={"budgets": config.budgets.model_copy(update={"max_legs": 1})})
    generation._generate_for_underlying("volatility", plan, "XYZ", one_leg)
    empty_underlying = underlyings[0].model_copy(update={"last": None, "ask": None, "bid": None})
    with pytest.raises(ValueError):
        planning.TemplatePlan(contracts, quotes, (empty_underlying,), records("validated_market_belief_state"), config).spot("XYZ")


def test_mutation_remaining_branches(monkeypatch: pytest.MonkeyPatch):
    config = advanced_config()
    candidates = records("raw_strategy_candidate_panel")
    parent = next(item for item in candidates if item.legs[0].instrument_type is InstrumentType.OPTION)
    contracts = records("eligible_option_contract_panel")
    quotes = {item.contract_id: item for item in records("eligible_option_quote_panel")}
    slices = mutation_operators.contract_slices(contracts)
    mutation_operators.move_strikes(parent, slices, quotes, config)

    leg = parent.legs[0]
    duplicate = parent.model_copy(update={"legs": (leg, leg.model_copy(update={"leg_id": "dup"}))})
    assert mutation_operators.remove_redundant(duplicate, config) is not None
    target_contract = next(item for item in contracts if item.contract_id != leg.instrument_id and item.option_type == leg.option_type)
    assert mutation_operators._replace_strike(parent, 0, target_contract, {}, config) is None
    no_side = quotes[target_contract.contract_id].model_copy(update={"ask": None, "bid": None})
    assert mutation_operators._replace_strike(parent, 0, target_contract, {target_contract.contract_id: no_side}, config) is None

    assert mutation_engine.mutate_candidates((), contracts, tuple(quotes.values()), records("validated_underlying_panel"), config) == ((), (), ())
    application = advanced_result()["outputs"]["mutation_application_panel_raw"].records[0]
    monkeypatch.setattr(mutation_engine, "_mutate_parent", lambda *a: [(parent, application)])
    children, _, _ = mutation_engine.mutate_candidates((parent,), contracts, tuple(quotes.values()), records("validated_underlying_panel"), config)
    assert children == ()
    assert mutation_engine._apply_operator(object(), parent, slices, quotes, {}, config) == []

    rejected_candidate = parent.model_copy(update={"legs": parent.legs * (config.budgets.max_legs + 1)})
    accepted, rejected = mutation_validation.complexity_gate((rejected_candidate,), (), config)
    assert not accepted and rejected
    two_exp = parent.model_copy(update={"legs": tuple(leg.model_copy(update={"expiration": leg.expiration + timedelta(days=i)}) for i, leg in enumerate(parent.legs * 3))})
    low_exp = config.model_copy(update={"budgets": config.budgets.model_copy(update={"max_expirations": 1})})
    assert mutation_validation._complexity_reasons(two_exp, set(), low_exp)
    high_qty = parent.model_copy(update={"legs": (leg.model_copy(update={"quantity": D(config.budgets.max_quantity + 1)}),)})
    assert mutation_validation._complexity_reasons(high_qty, set(), config)


def test_target_solver_and_basis_remaining_branches(monkeypatch: pytest.MonkeyPatch):
    config = advanced_config()
    belief = records("validated_market_belief_state")[0]
    contracts = records("eligible_option_contract_panel")
    quotes = records("eligible_option_quote_panel")
    # Missing-price call is skipped, while later contracts keep the loop active.
    qmap = {q.contract_id: q for q in quotes}
    first_call = next(c for c in contracts if c.option_type is OptionType.CALL)
    qmap[first_call.contract_id] = qmap[first_call.contract_id].model_copy(update={"bid": None, "ask": None, "last": None})
    market_implied._call_points(contracts, tuple(qmap.values()))
    points = tuple((c, D("1")) for c in contracts if c.option_type is OptionType.CALL)[:3]
    monkeypatch.setattr(market_implied, "_curvature_masses", lambda _: ((D("90"),), (D("0"),)))
    assert market_implied._implied_state(belief, points, DECISION_TIME).status is CalculationStatus.BLOCKED

    implied = records("market_implied_state_panel")[0]
    raw = target_builder._raw_target(TargetPayoffMode.BELIEF_RATIO, records("raw_strategy_candidate_panel")[0].objective_family, implied.state_grid, implied.risk_neutral_probabilities, D("100"), implied, config)
    assert raw[0]

    target = records("target_payoff_panel")[0]
    underlying = records("validated_underlying_panel")[0]
    first = contracts[0]
    first_quote = next(q for q in quotes if q.contract_id == first.contract_id)
    ask_only = first_quote.model_copy(update={"bid": None})
    bid_only = first_quote.model_copy(update={"ask": None, "bid": first_quote.bid})
    assert basis._basis_legs(target, [first], {first.contract_id: ask_only}, underlying, config)
    assert basis._basis_legs(target, [first], {first.contract_id: bid_only}, underlying, config)
    disabled = config.model_copy(update={"strategy": config.strategy.model_copy(update={"allow_long_underlying": False, "allow_short_underlying": False})})
    assert basis._underlying_legs(underlying, disabled) == []

    candidate = records("raw_strategy_candidate_panel")[0]
    trace = records("template_generation_trace_panel")[0]
    tiny = config.model_copy(update={"budgets": config.budgets.model_copy(update={"max_candidates_before_dedup": 1})})
    merged, traces = orchestrator.combine_candidate_universe((candidate, candidate.model_copy(update={"candidate_id": "other"})), (trace, trace.model_copy(update={"candidate_id": "missing"})), (), (), (), (), tiny)
    assert len(merged) == 1 and len(traces) <= 1

    result = records("solver_result_panel")[0]
    basis_records = records("replication_basis_panel")
    assert orchestrator._legs(result.model_copy(update={"quantities": (result.quantities[0].model_copy(update={"basis_id": "missing"}),)}), {}, config) == ()
    by_id = {b.basis_id: b for b in basis_records}
    same_instrument = next(iter(by_id.values()))
    other_side = same_instrument.model_copy(update={"basis_id": "other-side", "leg": same_instrument.leg.model_copy(update={"side": Side.SHORT if same_instrument.leg.side is Side.LONG else Side.LONG})})
    conflict_result = result.model_copy(update={"quantities": (
        result.quantities[0].model_copy(update={"basis_id": same_instrument.basis_id, "quantity": D("1")}),
        result.quantities[0].model_copy(update={"basis_id": other_side.basis_id, "quantity": D("1")}),
    )})
    assert orchestrator._legs(conflict_result, {same_instrument.basis_id: same_instrument, other_side.basis_id: other_side}, config) == ()

    problem = records("strategy_synthesis_problem_panel")[0]
    basis_for_problem = tuple(x for x in basis_records if x.target_payoff_id == problem.target_payoff_id)
    data = solver_common.solver_data(problem.model_copy(update={"max_legs": 1}), {x.basis_id: x for x in basis_for_problem})
    monkeypatch.setattr(solver_exact, "_ordered_basis", lambda *_: [0, 1])
    monkeypatch.setattr(solver_exact, "_integer_options", lambda *_: [(1,), (1,)])
    solver_exact.solve_integer(data, None, config)
    zero_iter = config.model_copy(update={"solver": config.solver.model_copy(update={"local_search_iterations": 0})})
    solver_search.solve_local(data, [], zero_iter)
    zero_leg_data = solver_common.SolverData(problem=data.problem.model_copy(update={"max_legs": 0}), basis=data.basis, x=data.x, y=data.y, w=data.w)
    solver_search._expand_beam(zero_leg_data, [(0.0, tuple(0.0 for _ in data.basis))], config)


def test_pricing_pathwise_feasibility_and_archive_remaining():
    config = advanced_config()
    candidate = records("raw_strategy_candidate_panel")[0]
    quotes = records("eligible_option_quote_panel")
    quote_map = {q.contract_id: q for q in quotes}
    missing_leg = candidate.legs[0].model_copy(update={"instrument_id": "MISSING"})
    mixed = candidate.model_copy(update={"legs": (missing_leg,) + candidate.legs})
    s7._liquidity_inputs(mixed, quote_map)
    belief = records("validated_market_belief_state")[0]
    cost = records("strategy_cost_liquidity_panel")[0]
    assert s7.scenario_records((candidate,), (), (cost,)) == ()
    assert s7.ambiguity_records(()) == ()
    observation = records("validated_underlying_panel")[0].model_copy(update={"last": None, "ask": None, "bid": None})
    with pytest.raises(ValueError):
        s7._spot(observation)

    expired_none = candidate.legs[0].model_copy(update={"expiration": None})
    invalid_candidate = candidate.model_copy(update={"legs": (expired_none,)})
    _, status, reason = pathwise._mark_candidate(invalid_candidate, D("100"), D("0.5"), quote_map, config)
    assert status is CalculationStatus.UNAVAILABLE and reason

    leg = candidate.legs[0]
    duplicate = leg.model_copy(update={"leg_id": leg.leg_id})
    extra_exchange = leg.model_copy(update={"leg_id": "exchange", "exchange": "OTHER"})
    extra_exp = leg.model_copy(update={"leg_id": "expiry", "expiration": leg.expiration + timedelta(days=1)})
    structural = candidate.model_copy(update={"legs": (leg, duplicate, extra_exchange, extra_exp)})
    restrictive = config.model_copy(update={"budgets": config.budgets.model_copy(update={"max_legs": 1, "max_expirations": 1})})
    reasons = qualification_gates._structural_reasons(structural, restrictive)
    assert {"P6_COMPLEXITY_BUDGET_EXCEEDED", "P6_REDUNDANT_LEG", "P6_MIXED_EXCHANGE_UNSUPPORTED"} <= set(reasons)

    risk = records("strategy_risk_panel")[0]
    zero_cost = cost.model_copy(update={"conservative_entry_cost": D("0")})
    assert archive._niche_id(candidate, risk, zero_cost, config.publication.archive_mode)
    qualification = records("strategy_qualification_panel")[0].model_copy(update={"qualified": True})
    cancelling = candidate.model_copy(update={"legs": (leg, leg.model_copy(update={"leg_id": "opp", "side": Side.SHORT if leg.side is Side.LONG else Side.LONG}) )})
    assert canonicalization.canonicalize_candidates((cancelling,), (qualification.model_copy(update={"candidate_id": cancelling.candidate_id}),), config) == ()

def test_final_branch_completeness():
    # P5 V1 accepts the primary identity field without using the fallback.
    primary = {"artifact_id": "v1", "records": [{
        "underlying": "XYZ", "available_at": DECISION_TIME.isoformat(),
        "horizon_days": 2,
        "confidence": "0.5",
    }]}
    assert p5.parse_p5_beliefs({"underlying_forecast_panel": primary}, DECISION_TIME, "M")[0].underlying_id == "XYZ"

    config = advanced_config("TEMPLATE_ONLY")
    contracts = records("eligible_option_contract_panel")
    quotes = records("eligible_option_quote_panel")
    underlyings = records("validated_underlying_panel")
    plan = planning.TemplatePlan(contracts, quotes, underlyings, records("validated_market_belief_state"), config)
    calls = tuple(item for item in plan.contracts("XYZ", OptionType.CALL) if item.strike != D("100"))
    puts = plan.contracts("XYZ", OptionType.PUT)
    captured = []
    family_generators.generate_volatility(plan, "XYZ", calls, puts, config, lambda *x: captured.append(x))
    assert captured and all(item[0].value != "LONG_STRADDLE" for item in captured)

    parent = next(
        item for item in records("raw_strategy_candidate_panel")
        if len(item.legs) == 1
        and item.legs[0].instrument_type is InstrumentType.OPTION
        and item.legs[0].strike == D("100")
    )
    slices = mutation_operators.contract_slices(contracts)
    quote_map = {item.contract_id: item for item in quotes}
    adjacent = next(
        item for item in contracts
        if item.option_type == parent.legs[0].option_type
        and item.strike == D("90")
    )
    quote_map.pop(adjacent.contract_id)
    mutation_operators.move_strikes(parent, slices, quote_map, advanced_config())

    no_depth = quote_map[parent.legs[0].instrument_id].model_copy(
        update={"bid_size": None, "ask_size": None, "volume": None, "open_interest": None}
    )
    spreads, depths = s7._liquidity_inputs(parent, {parent.legs[0].instrument_id: no_depth})
    assert spreads and not depths
