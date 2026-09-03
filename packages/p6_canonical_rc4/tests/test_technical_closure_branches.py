from __future__ import annotations

import json
from functools import lru_cache
import math
import subprocess
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from random import Random
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from conftest import DECISION_TIME, build_configuration, build_inputs, external_artifact
from quant_pipeline.phase_06_strategy_synthesis.boundaries import p5
from quant_pipeline.phase_06_strategy_synthesis.domain.enums import (
    ArchiveMode,
    CalculationStatus,
    CapabilityStatus,
    ExerciseStyle,
    InstrumentType,
    LegRole,
    MarginMethod,
    MutationOperator,
    ObjectiveFamily,
    OptionType,
    QuoteQuality,
    SettlementType,
    Side,
    SolverStatus,
    TargetPayoffMode,
)
from quant_pipeline.phase_06_strategy_synthesis.domain.greeks import (
    option_greeks,
    option_price,
)
from quant_pipeline.phase_06_strategy_synthesis.domain.identity import integer_scale
from quant_pipeline.phase_06_strategy_synthesis.domain.models import (
    CandidateQualification,
    CostLiquidityRecord,
    ExecutableQuote,
    GreekState,
    MarketBeliefState,
    MarketImpliedState,
    MutationApplication,
    OptionContractReference,
    StrategyCandidate,
    StrategyLeg,
    StrategyPayoffRecord,
    TargetPayoffQualification,
    TargetPayoffRecord,
    UnderlyingObservation,
)
from quant_pipeline.phase_06_strategy_synthesis.domain.payoff import (
    break_even_points,
    leg_terminal_value,
)
from quant_pipeline.phase_06_strategy_synthesis.domain.statistics import (
    expected_shortfall,
    weighted_quantile,
)
from quant_pipeline.phase_06_strategy_synthesis.foundation.artifacts import (
    ArtifactEnvelope,
    ArtifactStatus,
    FrozenModel,
    build_artifact,
)
from quant_pipeline.phase_06_strategy_synthesis.foundation.configuration import (
    Phase6RunConfiguration,
)
from quant_pipeline.phase_06_strategy_synthesis.foundation.contracts import (
    external_artifact_id,
    parse_external_records,
)
from quant_pipeline.phase_06_strategy_synthesis.foundation.errors import Phase6ContractError
from quant_pipeline.phase_06_strategy_synthesis.foundation.hashing import (
    canonical_sha256,
    canonical_value,
)
from quant_pipeline.phase_06_strategy_synthesis.orchestration.phase_runner import run_phase
from quant_pipeline.phase_06_strategy_synthesis.subphase_01_boundary_market_snapshot import services as s1
from quant_pipeline.phase_06_strategy_synthesis.subphase_02_canonical_strategy_domain.services import (
    _contract_rejection_reason,
)
from quant_pipeline.phase_06_strategy_synthesis.subphase_03_template_generation import (
    builders,
    family_generators,
    generation,
    planning,
)
from quant_pipeline.phase_06_strategy_synthesis.subphase_04_mutation_deformation import (
    mutation_engine,
    mutation_operators,
    validation as mutation_validation,
)
from quant_pipeline.phase_06_strategy_synthesis.subphase_05_target_payoff import (
    market_implied,
    target_builder,
    target_regularization,
)
from quant_pipeline.phase_06_strategy_synthesis.subphase_06_inverse_design import (
    basis,
    orchestrator,
    solver_common,
    solver_exact,
    solver_search,
)
from quant_pipeline.phase_06_strategy_synthesis.subphase_07_pricing_scenario_evaluation import (
    pathwise,
    services as s7,
)
from quant_pipeline.phase_06_strategy_synthesis.subphase_08_feasibility_defined_risk import (
    qualification_gates,
    risk_qualification,
)
from quant_pipeline.phase_06_strategy_synthesis.subphase_09_canonicalization_diversity import (
    archive,
    canonicalization,
)

D = Decimal
UTC = timezone.utc


class Record(FrozenModel):
    value: int


def advanced_config(mode: str = "QUALITY_DIVERSITY") -> Phase6RunConfiguration:
    value = build_configuration()
    value["operational_mode"] = mode
    value["budgets"] = {
        "max_solver_seconds": 1,
        "max_solver_nodes": 50,
        "max_mutations": 10,
        "max_candidates_before_dedup": 80,
    }
    value["solver"] = {
        "maximum_basis_size": 6,
        "continuous_iterations": 4,
        "beam_width": 3,
        "beam_depth": 2,
        "local_search_iterations": 3,
        "evolutionary_population": 4,
        "evolutionary_generations": 2,
    }
    return Phase6RunConfiguration.model_validate(value)


@lru_cache(maxsize=1)
def advanced_result():
    return run_phase(build_inputs(), advanced_config().model_dump(mode="json"))


def records(name: str):
    return advanced_result()["outputs"][name].records


def test_p5_v1_v2_and_errors():
    module = "P6.S1.M01"
    with pytest.raises(Phase6ContractError):
        p5.parse_p5_beliefs({}, DECISION_TIME, module)

    wrong = build_inputs()["market_belief_state"]
    wrong = deepcopy(wrong)
    wrong["records"][0]["decision_time"] = (DECISION_TIME + timedelta(seconds=1)).isoformat()
    wrong["content_sha256"] = canonical_sha256(wrong["records"])
    with pytest.raises(Phase6ContractError) as exc:
        p5.parse_p5_beliefs({"market_belief_state": wrong}, DECISION_TIME, module)
    assert exc.value.reason_code == "P6_MARKET_CLOCK_MISMATCH"

    for invalid in (None, {"records": "bad"}):
        with pytest.raises(Phase6ContractError):
            p5.parse_p5_beliefs({"underlying_forecast_panel": invalid}, DECISION_TIME, module)

    missing = {"artifact_id": "v1", "records": [{"available_at": DECISION_TIME.isoformat()}]}
    with pytest.raises(Phase6ContractError):
        p5.parse_p5_beliefs({"underlying_forecast_panel": missing}, DECISION_TIME, module)

    future = {
        "artifact_id": "v1",
        "records": [{
            "underlying_id": "XYZ",
            "available_at": (DECISION_TIME + timedelta(seconds=1)).isoformat(),
            "horizon_days": 1,
            "confidence": "0.5",
        }],
    }
    with pytest.raises(Phase6ContractError) as exc:
        p5.parse_p5_beliefs({"underlying_forecast_panel": future}, DECISION_TIME, module)
    assert exc.value.reason_code == "P6_P5_FORECAST_FUTURE_DATED"

    valid = {
        "artifact_id": "v1",
        "records": [{
            "underlying_id": "XYZ",
            "available_at": DECISION_TIME.isoformat(),
            "horizon_days": 5,
            "forecast_confidence": "0.7",
        }],
    }
    parsed = p5.parse_p5_beliefs({"underlying_forecast_panel": valid}, DECISION_TIME, module)
    assert parsed[0].scenario_capability is CapabilityStatus.LIMITED


def test_foundation_contract_hashing_and_artifact_validation():
    belief = records("validated_market_belief_state")[0]
    artifact = build_artifact(
        artifact_type="beliefs",
        producer_module_id="test",
        run_id="r",
        cycle_id="c",
        decision_time=DECISION_TIME,
        created_at=DECISION_TIME,
        available_at=DECISION_TIME,
        records=(belief,),
    )
    parsed = parse_external_records(artifact, MarketBeliefState, "belief", "test")
    assert parsed == (belief,)
    assert external_artifact_id(artifact, "belief", "test") == artifact.artifact_id

    with pytest.raises(Phase6ContractError):
        parse_external_records(7, MarketBeliefState, "belief", "test")
    with pytest.raises(Phase6ContractError):
        parse_external_records({"records": "bad"}, MarketBeliefState, "belief", "test")
    with pytest.raises(Phase6ContractError):
        external_artifact_id({}, "belief", "test")

    @dataclass(frozen=True)
    class Sample:
        value: int

    assert canonical_value(Sample(1)) == {"value": 1}
    assert canonical_value(date(2026, 1, 1)) == "2026-01-01"
    assert canonical_value({3, 1, 2}) == [1, 2, 3]
    with pytest.raises(ValueError):
        canonical_value(datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        canonical_value(math.inf)

    common = dict(
        artifact_id="a",
        artifact_type="x",
        schema_version="6",
        producer_phase="P6",
        producer_module_id="m",
        run_id="r",
        cycle_id="c",
        decision_time=DECISION_TIME,
        created_at=DECISION_TIME,
        available_at=DECISION_TIME,
        content_sha256=canonical_sha256((Record(value=1),)),
        record_count=1,
        lineage_id="l",
        status=ArtifactStatus.COMPLETE,
        records=(Record(value=1),),
    )
    with pytest.raises(ValidationError):
        ArtifactEnvelope[Record](**{**common, "available_at": DECISION_TIME - timedelta(seconds=1)})
    with pytest.raises(ValidationError):
        ArtifactEnvelope[Record](**{**common, "record_count": 2})
    with pytest.raises(ValidationError):
        ArtifactEnvelope[Record](**{**common, "content_sha256": "0" * 64})
    with pytest.raises(ValidationError):
        ArtifactEnvelope[Record](**{**common, "records": (), "record_count": 0, "content_sha256": canonical_sha256(())})


def test_market_model_and_synthesis_validation_branches():
    underlying = records("validated_underlying_panel")[0]
    with pytest.raises(ValidationError):
        UnderlyingObservation.model_validate({**underlying.model_dump(), "bid": None, "ask": None, "last": None})

    belief = records("validated_market_belief_state")[0]
    with pytest.raises(ValidationError):
        MarketBeliefState.model_validate({
            **belief.model_dump(),
            "scenarios": [],
            "scenario_capability": "AVAILABLE",
        })
    with pytest.raises(ValidationError):
        MarketBeliefState.model_validate({
            **belief.model_dump(),
            "ambiguity_capability": "AVAILABLE",
            "ambiguity_probabilities": [["1"]],
        })
    with pytest.raises(ValidationError):
        MarketBeliefState.model_validate({
            **belief.model_dump(),
            "ambiguity_capability": "AVAILABLE",
            "ambiguity_probabilities": [["0.1", "0.2", "0.3"]],
        })
    with pytest.raises(ValidationError):
        MarketBeliefState.model_validate({
            **belief.model_dump(),
            "ambiguity_capability": "UNAVAILABLE",
            "ambiguity_probabilities": [["0.2", "0.5", "0.3"]],
        })

    implied = records("market_implied_state_panel")[0]
    with pytest.raises(ValidationError):
        MarketImpliedState.model_validate({**implied.model_dump(), "state_grid": [], "risk_neutral_probabilities": [], "status": "AVAILABLE"})
    with pytest.raises(ValidationError):
        MarketImpliedState.model_validate({**implied.model_dump(), "risk_neutral_probabilities": ["0.1"] * len(implied.state_grid), "status": "AVAILABLE"})

    target = records("target_payoff_panel")[0]
    with pytest.raises(ValidationError):
        TargetPayoffRecord.model_validate({**target.model_dump(), "regularized_target_payoff": ["1"]})


def test_boundary_snapshot_quote_and_arbitrage_branches():
    quote = records("validated_option_quote_panel")[0]
    underlying = records("validated_underlying_panel")[0]
    contract = records("validated_option_contract_panel")[0]

    assert s1.quote_mid(quote) == (quote.bid + quote.ask) / 2
    assert s1.quote_mid(quote.model_copy(update={"bid": None, "ask": None})) == quote.last
    assert s1.quote_mid(quote.model_copy(update={"bid": None, "ask": None, "last": None})) is None

    assert s1.classify_quote(quote).quote_quality is QuoteQuality.TWO_SIDED_EXECUTABLE
    assert s1.classify_quote(quote.model_copy(update={"ask": None})).quote_quality is QuoteQuality.ONE_SIDED_BID
    assert s1.classify_quote(quote.model_copy(update={"bid": None})).quote_quality is QuoteQuality.ONE_SIDED_ASK
    assert s1.classify_quote(quote.model_copy(update={"bid": None, "ask": None})).quote_quality is QuoteQuality.TRADE_ONLY
    assert s1.classify_quote(quote.model_copy(update={"bid": None, "ask": None, "last": None})).quote_quality is QuoteQuality.UNAVAILABLE

    unknown = quote.model_copy(update={"contract_id": "UNKNOWN"})
    violations = s1.static_arbitrage_diagnostics((contract,), (unknown,), (underlying,))
    assert any(item.violation_type == "UNKNOWN_CONTRACT" for item in violations)

    intrinsic_bad = quote.model_copy(update={"bid": D("0"), "ask": D("0.1"), "last": D("0.05")})
    violations = s1.static_arbitrage_diagnostics((contract,), (intrinsic_bad,), (underlying,))
    assert any(item.violation_type == "INTRINSIC_BOUND" for item in violations)

    contracts = records("validated_option_contract_panel")
    quotes = list(records("validated_option_quote_panel"))
    by_id = {q.contract_id: q for q in quotes}
    by_id["XYZ-CALL-90"] = by_id["XYZ-CALL-90"].model_copy(update={"bid": D("25"), "ask": D("25")})
    by_id["XYZ-PUT-110"] = by_id["XYZ-PUT-110"].model_copy(update={"bid": D("1"), "ask": D("1")})
    by_id["XYZ-CALL-100"] = by_id["XYZ-CALL-100"].model_copy(update={"bid": D("30"), "ask": D("30")})
    violations = s1.static_arbitrage_diagnostics(contracts, tuple(by_id.values()), (underlying,))
    kinds = {item.violation_type for item in violations}
    assert "VERTICAL_MONOTONICITY" in kinds
    assert "BUTTERFLY_CONVEXITY" in kinds


def test_contract_lifecycle_reasons():
    contract = records("validated_option_contract_panel")[0]
    quote = records("validated_option_quote_panel")[0]
    config = advanced_config("TEMPLATE_ONLY")
    assert _contract_rejection_reason(contract.model_copy(update={"first_trade_date": DECISION_TIME + timedelta(days=1)}), quote, config) == "P6_CONTRACT_NOT_LISTED"
    assert _contract_rejection_reason(contract.model_copy(update={"expiration": DECISION_TIME}), quote, config) == "P6_CONTRACT_EXPIRED"
    assert _contract_rejection_reason(contract.model_copy(update={"last_trade_date": DECISION_TIME - timedelta(seconds=1)}), quote, config) == "P6_CONTRACT_EXPIRED"
    assert _contract_rejection_reason(contract.model_copy(update={"contract_status": "SUSPENDED"}), quote, config) == "P6_CONTRACT_INVALID_AT_DECISION"
    assert _contract_rejection_reason(contract.model_copy(update={"settlement_type": SettlementType.PHYSICAL}), quote, config) is None


def test_payoff_greeks_statistics_and_identity_branches():
    candidate = records("raw_strategy_candidate_panel")[0]
    option = candidate.legs[0]
    cash = option.model_copy(update={"instrument_type": InstrumentType.CASH, "strike": None, "option_type": None})
    assert leg_terminal_value(cash, D("100")) != 0
    invalid = option.model_copy(update={"strike": None})
    with pytest.raises(ValueError):
        leg_terminal_value(invalid, D("100"))
    with pytest.raises(ValueError):
        option_greeks(invalid, D("100"), D("0.2"), D("0.1"), D("0.05"), D("0"))
    with pytest.raises(ValueError):
        option_greeks(option, D("0"), D("0.2"), D("0.1"), D("0.05"), D("0"))
    with pytest.raises(ValueError):
        option_price(invalid, D("100"), D("0.2"), D("0.1"), D("0.05"), D("0"))
    with pytest.raises(ValueError):
        option_price(option, D("0"), D("0.2"), D("0.1"), D("0.05"), D("0"))

    assert integer_scale((option.model_copy(update={"quantity": D("2")}),)) == 2
    assert integer_scale((option.model_copy(update={"quantity": D("2.5")}),)) == 1
    assert weighted_quantile([D("1"), D("2")], [D("0.1"), D("0.1")], D("0.99")) == D("2")
    assert expected_shortfall([D("1")], [D("0")]) == D("0")
    roots = break_even_points((D("0"), D("1"), D("2")), (D("0"), D("1"), D("0")))
    assert D("0") in roots and D("2") in roots


def test_template_branches_and_builder_errors():
    config = advanced_config("TEMPLATE_ONLY")
    contracts = records("eligible_option_contract_panel")
    calls = tuple(item for item in contracts if item.option_type is OptionType.CALL)
    puts = tuple(item for item in contracts if item.option_type is OptionType.PUT)
    plan = planning.TemplatePlan(
        contracts,
        records("eligible_option_quote_panel"),
        records("validated_underlying_panel"),
        records("validated_market_belief_state"),
        config,
    )
    collected = []

    def add(*args):
        collected.append(args)

    no_underlying = config.model_copy(update={"strategy": config.strategy.model_copy(update={"allow_long_underlying": False, "allow_short_underlying": True})})
    family_generators.generate_single(plan, "XYZ", calls, puts, no_underlying, add)
    assert any(item[0].value == "SHORT_UNDERLYING" for item in collected)

    family_generators._add_call_butterfly(calls[:2], {}, add)
    family_generators._add_call_condor(calls[:3], {}, add)
    family_generators._add_iron_structures(calls[:1], puts[:1], {}, add)
    family_generators._add_protected_ratio(calls[:2], {}, add)

    quote = records("eligible_option_quote_panel")[0]
    with pytest.raises(ValueError):
        builders.option_leg(calls[0], quote.model_copy(update={"ask": None}), Side.LONG, 1, LegRole.CORE)
    underlying = records("validated_underlying_panel")[0]
    with pytest.raises(ValueError):
        builders.underlying_leg(planning.TemplatePlan(contracts, records("eligible_option_quote_panel"), (underlying.model_copy(update={"ask": None}),), records("validated_market_belief_state"), config), "XYZ", Side.LONG, LegRole.CORE)
    assert planning.TemplatePlan(contracts, records("eligible_option_quote_panel"), (underlying.model_copy(update={"bid": None, "ask": None, "last": D("99")}),), records("validated_market_belief_state"), config).spot("XYZ") == D("99")

    with pytest.raises(ValueError):
        generation._generate_for_underlying("UNKNOWN", plan, "XYZ", config)


def test_target_builder_modes_regularization_and_market_implied():
    config = advanced_config()
    belief = records("validated_market_belief_state")[0]
    underlying = records("validated_underlying_panel")[0]
    implied = records("market_implied_state_panel")[0]

    empty = belief.model_copy(update={"scenarios": (), "scenario_capability": CapabilityStatus.LIMITED})
    assert target_builder._belief_targets(empty, implied, D("100"), config) == []

    fallback_policy = config.target_payoff.model_copy(update={"modes": (TargetPayoffMode.USER_POLICY,)})
    fallback_config = config.model_copy(update={"target_payoff": fallback_policy})
    assert target_builder._mode_for_objective(ObjectiveFamily.DIRECTIONAL_UP, fallback_config) is TargetPayoffMode.USER_POLICY

    grid = (D("80"), D("100"), D("120"))
    probs = (D("0.2"), D("0.5"), D("0.3"))
    unavailable = target_builder._belief_ratio_target(grid, probs, None, config)
    assert unavailable[1] is CalculationStatus.UNAVAILABLE
    available = target_builder._belief_ratio_target(grid, probs, implied, config)
    if implied.status is CalculationStatus.AVAILABLE:
        assert available[1] is CalculationStatus.AVAILABLE

    expected = target_builder._raw_target(TargetPayoffMode.EXPECTED_UTILITY, ObjectiveFamily.DIRECTIONAL_UP, grid, probs, D("100"), implied, config)
    assert expected[1] is CalculationStatus.AVAILABLE
    short_vol = target_builder._objective_target(ObjectiveFamily.SHORT_VOLATILITY_DEFINED_RISK, grid, D("100"), D("20"))
    assert short_vol[1] >= short_vol[0]
    assert target_builder._interpolate_probabilities(grid, grid, probs, D("0.0001")) == probs
    with pytest.raises(ValueError):
        target_builder._spot(underlying.model_copy(update={"bid": None, "ask": None, "last": None}))

    target = records("target_payoff_panel")[0]
    unavailable_target = target.model_copy(update={"status": CalculationStatus.UNAVAILABLE, "reason_code": None, "raw_target_payoff": (), "regularized_target_payoff": (), "terminal_state_grid": (), "scenario_probabilities": ()})
    unchanged, report = target_regularization._regularize_target(unavailable_target, config)
    assert unchanged is unavailable_target and not report.finite
    assert target_regularization._qualification_reasons(unavailable_target, False, False, False) == (
        "P6_TARGET_PAYOFF_UNAVAILABLE",
        "P6_PAYOFF_NON_FINITE",
        "P6_TARGET_PAYOFF_UNBOUNDED",
        "P6_TARGET_PAYOFF_CONFIDENCE_BELOW_MINIMUM",
    )
    assert target_regularization._smooth((D("1"), D("2")), D("0.2")) == (D("1"), D("2"))
    assert target_regularization._normalize((D("0"), D("0"))) == (D("0"), D("0"))

    contracts = records("eligible_option_contract_panel")
    quotes = records("eligible_option_quote_panel")
    few = tuple(item for item in contracts if item.option_type is OptionType.CALL)[:2]
    states = market_implied.estimate_market_implied_states((belief,), few, quotes, DECISION_TIME)
    assert states[0].status is CalculationStatus.UNAVAILABLE
    duplicate_points = (
        (contracts[0], D("1")),
        (contracts[0].model_copy(update={"contract_id": "dup"}), D("1")),
        (contracts[1], D("1")),
    )
    grid2, masses = market_implied._curvature_masses(duplicate_points)
    assert isinstance(grid2, tuple) and isinstance(masses, tuple)
    blocked = market_implied._blocked_state(belief, duplicate_points, DECISION_TIME)
    assert blocked.status is CalculationStatus.BLOCKED


def test_mutation_operator_and_complexity_branches(monkeypatch):
    result = advanced_result()
    config = advanced_config()
    parent = records("raw_strategy_candidate_panel")[0]
    contracts = records("eligible_option_contract_panel")
    quotes = {item.contract_id: item for item in records("eligible_option_quote_panel")}
    slices = mutation_operators.contract_slices(contracts)

    non_option = parent.model_copy(update={"legs": (records("replication_basis_panel")[0].leg,)})
    assert mutation_operators.move_strikes(non_option, slices, quotes, config) == []
    unknown_leg = parent.legs[0].model_copy(update={"instrument_id": "UNKNOWN"})
    assert mutation_operators.move_strikes(parent.model_copy(update={"legs": (unknown_leg,)}), slices, quotes, config) == []

    maxed = parent.model_copy(update={"legs": tuple(leg.model_copy(update={"quantity": D(config.budgets.max_quantity)}) for leg in parent.legs)})
    assert mutation_operators.change_quantity(maxed, config) is None

    disabled = config.model_copy(update={"mutation": config.mutation.model_copy(update={"allow_underlying_overlay": False})})
    assert mutation_operators.add_underlying(parent, {}, disabled) is None
    with_underlying = non_option
    assert mutation_operators.add_underlying(with_underlying, {}, config) is None
    full = parent.model_copy(update={"legs": parent.legs * config.budgets.max_legs})
    assert mutation_operators.add_underlying(full, {}, config) is None
    assert mutation_operators.add_underlying(parent, {}, config) is None
    observation = records("validated_underlying_panel")[0]
    no_ask = observation.model_copy(update={"ask": None})
    assert mutation_operators.add_underlying(parent, {"XYZ": no_ask}, config) is None
    down = parent.model_copy(update={"objective_family": ObjectiveFamily.DIRECTIONAL_DOWN})
    assert mutation_operators._overlay_side(down) is Side.SHORT

    assert mutation_operators.remove_redundant(parent, config) is None
    leg = parent.legs[0]
    cancel = parent.model_copy(update={"legs": (leg, leg.model_copy(update={"leg_id": "opposite", "side": Side.LONG if leg.side is Side.SHORT else Side.SHORT}))})
    assert mutation_operators.remove_redundant(cancel, config) is None
    grouped = {("a", "OPTION"): D("-2"), ("b", "OPTION"): D("0")}
    exemplar = {("a", "OPTION"): leg, ("b", "OPTION"): leg}
    net = mutation_operators._materialize_netted_legs(grouped, exemplar)
    assert len(net) == 1 and net[0].side is Side.SHORT

    fingerprints = {canonical_sha256([{"x": 1}])}
    over_legs = parent.model_copy(update={"legs": parent.legs * (config.budgets.max_legs + 1)})
    reasons = mutation_validation._complexity_reasons(over_legs, set(), config)
    assert "P6_COMPLEXITY_BUDGET_EXCEEDED" in reasons
    duplicate = parent.model_copy(update={"legs": (leg, leg.model_copy(update={"leg_id": "dup"}))})
    duplicate_fingerprint = canonical_sha256(
        __import__("quant_pipeline.phase_06_strategy_synthesis.domain.identity", fromlist=["canonical_leg_payload"]).canonical_leg_payload(duplicate.legs)
    )
    assert "P6_EQUIVALENT_CANDIDATE" in mutation_validation._complexity_reasons(duplicate, {duplicate_fingerprint}, config)

    application = result["outputs"]["mutation_application_panel_raw"].records[0]
    invalid_application = application.model_copy(update={"child_candidate_id": "missing"})
    checked = mutation_validation.validate_mutation_traces((), (invalid_application,))
    assert not checked[0].valid


def test_basis_solver_pathwise_and_feasibility_branches(monkeypatch):
    result = advanced_result()
    config = advanced_config()
    target = records("target_payoff_panel")[0]
    qualification = records("target_payoff_qualification_report")[0]
    contracts = records("eligible_option_contract_panel")
    quotes = records("eligible_option_quote_panel")
    underlying = records("validated_underlying_panel")[0]

    assert basis.build_replication_basis((target,), (qualification.model_copy(update={"qualified": False}),), contracts, quotes, (underlying,), config) == ()
    one = contracts[0]
    quote_by_id = {q.contract_id: q for q in quotes}
    quote_by_id.pop(one.contract_id)
    legs = basis._basis_legs(target, [one], quote_by_id, underlying, config)
    assert all(item[0].instrument_id != one.contract_id for item in legs)
    no_underlying = basis._underlying_legs(None, config)
    assert no_underlying == []
    both = config.model_copy(update={"strategy": config.strategy.model_copy(update={"allow_short_underlying": True})})
    assert len(basis._underlying_legs(underlying, both)) == 2

    problem = records("strategy_synthesis_problem_panel")[0]
    basis_records = tuple(item for item in records("replication_basis_panel") if item.target_payoff_id == problem.target_payoff_id)
    data = solver_common.solver_data(problem, {item.basis_id: item for item in basis_records})
    assert data.basis
    unqualified_problems = solver_common.synthesis_problems((target,), (qualification.model_copy(update={"qualified": False}),), basis_records, config)
    assert unqualified_problems == ()

    monkeypatch.setattr(solver_exact, "_timed_out", lambda *_: True)
    timed = solver_exact.solve_continuous(data, config)
    assert timed.status is SolverStatus.TIMEOUT
    assert solver_exact._seed_map(None) == {}
    assert solver_search._seed_quantities(data, []) == [0.0] * len(data.basis)
    values = [1.0] * len(data.basis)
    solver_search._repair_leg_count(values, 1, Random(1))
    assert sum(value != 0 for value in values) <= 1

    candidate = records("raw_strategy_candidate_panel")[0]
    belief = records("validated_market_belief_state")[0]
    cost = records("strategy_cost_liquidity_panel")[0]
    assert pathwise.pathwise_records((candidate,), (), quotes, (cost,), config) == ()
    no_iv = {q.contract_id: q.model_copy(update={"implied_volatility": None}) for q in quotes}
    marks, status, reason = pathwise._candidate_path(candidate, (D("100"), D("101")), no_iv, cost, config)
    assert status is not CalculationStatus.AVAILABLE and reason
    american_leg = candidate.legs[0].model_copy(update={"exercise_style": ExerciseStyle.AMERICAN})
    american = candidate.model_copy(update={"legs": (american_leg,)})
    _, status, reason = pathwise._mark_candidate(american, D("100"), D("0.5"), {q.contract_id: q for q in quotes}, config)
    assert status is CalculationStatus.BLOCKED and reason == "P6_EXERCISE_STYLE_UNSUPPORTED"

    base_q = records("strategy_qualification_panel")[0]
    payoff = records("strategy_payoff_panel")[0]
    high_limits = config.model_copy(update={"risk": config.risk.model_copy(update={"maximum_loss_limit": D("1"), "maximum_entry_cost": D("1"), "minimum_liquidity_score": D("100000"), "maximum_relative_spread": D("0")})})
    margin_q = qualification_gates.apply_margin_gate((base_q,), (payoff,), high_limits)[0]
    assert "P6_MARGIN_LIMIT_EXCEEDED" in margin_q.reason_codes
    cost_record = records("strategy_cost_liquidity_panel")[0]
    liquidity_q = qualification_gates.apply_liquidity_gate((base_q,), (cost_record,), high_limits)[0]
    assert "P6_LIQUIDITY_BELOW_MINIMUM" in liquidity_q.reason_codes
    cost_q = qualification_gates.apply_cost_gate((base_q,), (cost_record,), high_limits)[0]
    assert "P6_COST_LIMIT_EXCEEDED" in cost_q.reason_codes


def test_archive_canonicalization_risk_and_publication_branches():
    config = advanced_config()
    qualification = records("strategy_qualification_panel")[0]
    candidate = next(
        item for item in records("synthesized_strategy_candidate_panel")
        if item.candidate_id == qualification.candidate_id
    )
    risk = records("strategy_risk_panel")[0]
    cost = records("strategy_cost_liquidity_panel")[0]
    assert archive._risk_bucket(D("0"))
    cluster = archive._niche_id(candidate, risk, cost, ArchiveMode.CLUSTER_ARCHIVE)
    cvt = archive._niche_id(candidate, risk, cost, ArchiveMode.CVT_ARCHIVE)
    assert cluster.startswith("CLUSTER|") and cvt.startswith("CVT|")

    assert canonicalization.canonical_legs(()) == ()
    leg = candidate.legs[0]
    zeroed = leg.model_copy(update={"quantity": D("0")})
    assert canonicalization.canonical_legs((zeroed,)) == ()

    payoff = records("strategy_payoff_panel")[0]
    qualification = records("strategy_qualification_panel")[0]
    final, risks, rejected = risk_qualification.final_sanity_and_risk(
        (qualification,), (candidate,), (payoff,), ()
    )
    assert not final[0].qualified and not risks and rejected

    cfg = build_configuration()
    cfg["publication"] = {"publish_legacy_p7_projection": False}
    result = run_phase(build_inputs(), cfg)
    assert "candidate_feature_base_panel" not in result["phase7_outputs"]


def test_cli_jsonable_and_module_entry(tmp_path):
    from quant_pipeline.phase_06_strategy_synthesis.cli import _jsonable

    @dataclass
    class Item:
        value: int

    assert _jsonable(Item(1)) == {"value": 1}
    assert _jsonable(Path("x")) == "x"

    root = Path(__file__).resolve().parents[1]
    inputs_path = tmp_path / "inputs.json"
    config_path = tmp_path / "config.json"
    output_path = tmp_path / "out.json"
    inputs_path.write_text(json.dumps(build_inputs(), default=str), encoding="utf-8")
    config_path.write_text(json.dumps(build_configuration(), default=str), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "quant_pipeline.phase_06_strategy_synthesis.cli",
            "--inputs",
            str(inputs_path),
            "--configuration",
            str(config_path),
            "--output",
            str(output_path),
        ],
        cwd=root,
        env={**dict(__import__("os").environ), "PYTHONPATH": str(root / "src")},
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert output_path.is_file()
