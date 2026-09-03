"""P8.S4.M01 candidate scenario PnL cube builder."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.special import ndtr

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.arrays import ScenarioSet

from ..arrays import ScenarioPnLCube, load_stress_npz
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.arrays import StressScenarioSet
from ..contracts import (
    CandidateEconomicPackage,
    EuropeanOptionLeg,
    FactorDefinition,
    LinearLeg,
    PnLPolicy,
    ScenarioArtifactBundle,
    ShockKind,
    ValuationQuality,
)
from ..errors import ContractIntegrityError, HashMismatchError, ValuationCapabilityError

MODULE_ID = "P8.S4.M01"


def _load_scenarios(
    bundle: ScenarioArtifactBundle,
    use_reduced: bool,
) -> tuple[ScenarioSet, StressScenarioSet]:
    root = Path(bundle.root_path)
    name = bundle.reduced_scenarios_file if use_reduced else bundle.full_scenarios_file
    expected = bundle.reduced_scenarios_sha256 if use_reduced else bundle.full_scenarios_sha256
    scenarios = ScenarioSet.load_npz(root / name)
    if scenarios.content_sha256() != expected:
        raise HashMismatchError(f"scenario artifact hash mismatch: {name}")
    stresses = load_stress_npz(root / bundle.stress_scenarios_file)
    if stresses.content_sha256() != bundle.stress_scenarios_sha256:
        raise HashMismatchError("stress scenario artifact hash mismatch")
    if scenarios.factor_ids != stresses.factor_ids or scenarios.step_labels != stresses.step_labels:
        raise ContractIntegrityError("nominal and stress coordinates differ")
    return scenarios, stresses


def _factor_index(factor_ids: tuple[str, ...], factor_id: str) -> int:
    try:
        return factor_ids.index(factor_id)
    except ValueError as exc:
        raise ValuationCapabilityError(f"factor {factor_id} is unavailable") from exc


def _cumulative(values: np.ndarray, definition: FactorDefinition) -> np.ndarray:
    if definition.shock_kind == ShockKind.LOG_RETURN:
        return np.cumsum(values, axis=1)
    if definition.shock_kind == ShockKind.SIMPLE_RETURN:
        if np.any(values <= -1.0):
            raise ValuationCapabilityError(
                f"simple return factor {definition.factor_id} contains value <= -1"
            )
        return np.cumprod(1.0 + values, axis=1) - 1.0
    return values


def _bs_price(
    spot: np.ndarray,
    strike: float,
    tau: np.ndarray,
    rate: np.ndarray,
    dividend: float,
    volatility: np.ndarray,
    is_call: bool,
) -> np.ndarray:
    tau_safe = np.maximum(tau, 1e-14)
    sqrt_tau = np.sqrt(tau_safe)
    d1 = (np.log(spot / strike) + (rate - dividend + 0.5 * volatility**2) * tau_safe) / (
        volatility * sqrt_tau
    )
    d2 = d1 - volatility * sqrt_tau
    discounted_spot = spot * np.exp(-dividend * tau_safe)
    discounted_strike = strike * np.exp(-rate * tau_safe)
    if is_call:
        price = discounted_spot * ndtr(d1) - discounted_strike * ndtr(d2)
        intrinsic = np.maximum(spot - strike, 0.0)
    else:
        price = discounted_strike * ndtr(-d2) - discounted_spot * ndtr(-d1)
        intrinsic = np.maximum(strike - spot, 0.0)
    return np.where(tau > 1e-12, price, intrinsic)


def _option_state(
    values: np.ndarray,
    factor_ids: tuple[str, ...],
    factor_map: dict[str, FactorDefinition],
    leg: EuropeanOptionLeg,
    policy: PnLPolicy,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    underlying_index = _factor_index(factor_ids, leg.underlying_factor_id)
    definition = factor_map[leg.underlying_factor_id]
    shock = _cumulative(values[:, :, underlying_index], definition)
    if definition.shock_kind == ShockKind.LOG_RETURN:
        spot = leg.spot * np.exp(shock)
    elif definition.shock_kind == ShockKind.SIMPLE_RETURN:
        spot = leg.spot * (1.0 + shock)
    else:
        spot = leg.spot + shock
    volatility = np.full_like(spot, leg.volatility)
    if leg.volatility_factor_id is not None:
        volatility += values[:, :, _factor_index(factor_ids, leg.volatility_factor_id)]
    rate = np.full_like(spot, leg.risk_free_rate)
    if leg.rate_factor_id is not None:
        rate += values[:, :, _factor_index(factor_ids, leg.rate_factor_id)]
    return (
        np.maximum(spot, policy.option_spot_floor),
        np.maximum(volatility, policy.option_volatility_floor),
        rate,
    )


def _option_leg_pnl(
    values: np.ndarray,
    factor_ids: tuple[str, ...],
    factor_map: dict[str, FactorDefinition],
    elapsed_years: np.ndarray,
    leg: EuropeanOptionLeg,
    policy: PnLPolicy,
) -> np.ndarray:
    spot, volatility, rate = _option_state(values, factor_ids, factor_map, leg, policy)
    tau = np.maximum(leg.time_to_expiry_years - elapsed_years[None, :], 0.0)
    initial = _bs_price(
        np.asarray([[leg.spot]]), leg.strike, np.asarray([[leg.time_to_expiry_years]]),
        np.asarray([[leg.risk_free_rate]]), leg.dividend_yield,
        np.asarray([[leg.volatility]]), leg.option_type.value == "CALL",
    )[0, 0]
    repriced = _bs_price(
        spot, leg.strike, tau, rate, leg.dividend_yield, volatility,
        leg.option_type.value == "CALL",
    )
    return leg.quantity_per_unit * leg.contract_multiplier * (repriced - float(initial))


def _value_leg(
    values: np.ndarray,
    factor_ids: tuple[str, ...],
    factor_map: dict[str, FactorDefinition],
    elapsed: np.ndarray,
    leg: LinearLeg | EuropeanOptionLeg,
    policy: PnLPolicy,
) -> tuple[np.ndarray, ValuationQuality]:
    if isinstance(leg, LinearLeg):
        index = _factor_index(factor_ids, leg.factor_id)
        shock = _cumulative(values[:, :, index], factor_map[leg.factor_id])
        return leg.quantity_per_unit * leg.pnl_per_factor_unit * shock, ValuationQuality.ANALYTIC_LINEAR
    if isinstance(leg, EuropeanOptionLeg):
        return _option_leg_pnl(values, factor_ids, factor_map, elapsed, leg, policy), ValuationQuality.FULL_REPRICING
    raise ValuationCapabilityError("unsupported candidate leg")


def _evaluate_legs(
    scenarios: ScenarioSet,
    stresses: StressScenarioSet,
    candidates: tuple[CandidateEconomicPackage, ...],
    factor_map: dict[str, FactorDefinition],
    elapsed: np.ndarray,
    policy: PnLPolicy,
) -> tuple[list[np.ndarray], list[np.ndarray], dict[str, ValuationQuality]]:
    nominal: list[np.ndarray] = []
    stressed: list[np.ndarray] = []
    quality_map: dict[str, ValuationQuality] = {}
    for candidate in candidates:
        qualities: list[ValuationQuality] = []
        for leg in candidate.legs:
            leg_pnl, quality = _value_leg(scenarios.values, scenarios.factor_ids, factor_map, elapsed, leg, policy)
            stress_pnl, _ = _value_leg(stresses.values, stresses.factor_ids, factor_map, elapsed, leg, policy)
            nominal.append(leg_pnl)
            stressed.append(stress_pnl)
            qualities.append(quality)
        quality_map[candidate.candidate_id] = (
            ValuationQuality.FULL_REPRICING
            if ValuationQuality.FULL_REPRICING in qualities
            else ValuationQuality.ANALYTIC_LINEAR
        )
    return nominal, stressed, quality_map


def _aggregate_candidate_pnl(
    leg_array: np.ndarray,
    candidates: tuple[CandidateEconomicPackage, ...],
) -> np.ndarray:
    result = np.empty((*leg_array.shape[:2], len(candidates)), dtype=np.float64)
    offset = 0
    for index, candidate in enumerate(candidates):
        end = offset + len(candidate.legs)
        result[:, :, index] = leg_array[:, :, offset:end].sum(axis=2)
        offset = end
    return result


def build_pnl_cube(
    bundle: ScenarioArtifactBundle,
    candidates: tuple[CandidateEconomicPackage, ...],
    factor_definitions: tuple[FactorDefinition, ...],
    step_year_fractions: tuple[float, ...],
    policy: PnLPolicy,
) -> tuple[ScenarioPnLCube, dict[str, ValuationQuality]]:
    scenarios, stresses = _load_scenarios(bundle, policy.use_reduced_scenarios)
    if len(step_year_fractions) != len(scenarios.step_labels):
        raise ContractIntegrityError("step_year_fractions do not match scenario steps")
    factor_map = {definition.factor_id: definition for definition in factor_definitions}
    if set(scenarios.factor_ids) - set(factor_map):
        raise ContractIntegrityError("factor definitions are incomplete")
    elapsed = np.asarray(step_year_fractions, dtype=np.float64)
    nominal, stressed, qualities = _evaluate_legs(
        scenarios, stresses, candidates, factor_map, elapsed, policy,
    )
    nominal_array = np.stack(nominal, axis=2) if nominal else np.empty((*scenarios.values.shape[:2], 0))
    stress_array = np.stack(stressed, axis=2) if stressed else np.empty((*stresses.values.shape[:2], 0))
    cube = ScenarioPnLCube(
        candidate_pnl=_aggregate_candidate_pnl(nominal_array, candidates),
        leg_pnl=nominal_array,
        stress_candidate_pnl=_aggregate_candidate_pnl(stress_array, candidates),
        stress_leg_pnl=stress_array,
        probabilities=scenarios.probabilities,
        scenario_ids=scenarios.scenario_ids,
        stress_ids=stresses.stress_ids,
        step_labels=scenarios.step_labels,
        candidate_ids=tuple(candidate.candidate_id for candidate in candidates),
        leg_ids=tuple(leg.leg_id for candidate in candidates for leg in candidate.legs),
        leg_candidate_ids=tuple(candidate.candidate_id for candidate in candidates for _ in candidate.legs),
    )
    return cube, qualities
