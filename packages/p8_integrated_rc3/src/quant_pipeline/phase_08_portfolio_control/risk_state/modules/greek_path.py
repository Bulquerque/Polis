"""P8.S4.M03 aggregate Greek and path exposure engine."""
from __future__ import annotations

import math

import numpy as np
from scipy.special import ndtr

from ..arrays import GreekPathArrays, ScenarioPnLCube
from ..contracts import (
    CandidateEconomicPackage,
    CandidatePosition,
    ComponentQuality,
    EuropeanOptionLeg,
    GreekPathSummary,
    GreekPolicy,
    GreekVector,
    LinearLeg,
    PhysicalPosition,
)
from ..errors import DualBookReconciliationError

MODULE_ID = "P8.S4.M03"
GREEK_NAMES = ("delta", "gamma", "vega", "theta", "rho")


def _normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def _option_greeks(leg: EuropeanOptionLeg) -> np.ndarray:
    sqrt_tau = math.sqrt(leg.time_to_expiry_years)
    d1 = (
        math.log(leg.spot / leg.strike)
        + (leg.risk_free_rate - leg.dividend_yield + 0.5 * leg.volatility**2)
        * leg.time_to_expiry_years
    ) / (leg.volatility * sqrt_tau)
    d2 = d1 - leg.volatility * sqrt_tau
    discount_dividend = math.exp(-leg.dividend_yield * leg.time_to_expiry_years)
    discount_rate = math.exp(-leg.risk_free_rate * leg.time_to_expiry_years)
    pdf = _normal_pdf(d1)
    if leg.option_type.value == "CALL":
        delta = discount_dividend * float(ndtr(d1))
        theta = -leg.spot * discount_dividend * pdf * leg.volatility / (2.0 * sqrt_tau)
        theta -= leg.risk_free_rate * leg.strike * discount_rate * float(ndtr(d2))
        theta += leg.dividend_yield * leg.spot * discount_dividend * float(ndtr(d1))
        rho = leg.strike * leg.time_to_expiry_years * discount_rate * float(ndtr(d2))
    else:
        delta = discount_dividend * (float(ndtr(d1)) - 1.0)
        theta = -leg.spot * discount_dividend * pdf * leg.volatility / (2.0 * sqrt_tau)
        theta += leg.risk_free_rate * leg.strike * discount_rate * float(ndtr(-d2))
        theta -= leg.dividend_yield * leg.spot * discount_dividend * float(ndtr(-d1))
        rho = -leg.strike * leg.time_to_expiry_years * discount_rate * float(ndtr(-d2))
    gamma = discount_dividend * pdf / (leg.spot * leg.volatility * sqrt_tau)
    vega = leg.spot * discount_dividend * pdf * sqrt_tau
    scale = leg.quantity_per_unit * leg.contract_multiplier
    return np.asarray([delta, gamma, vega, theta, rho], dtype=np.float64) * scale


def _vector_from_model(model: GreekVector | None, scale: float) -> tuple[np.ndarray, np.ndarray]:
    vector = np.zeros(len(GREEK_NAMES), dtype=np.float64)
    coverage = np.zeros(len(GREEK_NAMES), dtype=np.float64)
    if model is None:
        return vector, coverage
    for index, name in enumerate(GREEK_NAMES):
        value = getattr(model, name)
        if value is not None:
            vector[index] = value * scale
            coverage[index] = 1.0
    return vector, coverage


def _candidate_greeks(
    candidate: CandidateEconomicPackage,
    max_error: float,
) -> tuple[np.ndarray, np.ndarray, bool]:
    vector = np.zeros(len(GREEK_NAMES), dtype=np.float64)
    coverage = np.zeros(len(GREEK_NAMES), dtype=np.float64)
    approximation_mismatch = False
    for leg in candidate.legs:
        if isinstance(leg, EuropeanOptionLeg):
            analytic = _option_greeks(leg)
            vector += analytic
            coverage += 1.0
            provided, provided_coverage = _vector_from_model(leg.provided_greeks_per_unit, 1.0)
            selected = provided_coverage > 0.0
            if np.any(selected):
                denominator = np.maximum(np.abs(analytic[selected]), 1e-10)
                approximation_mismatch |= bool(
                    np.max(np.abs(provided[selected] - analytic[selected]) / denominator) > max_error
                )
        elif isinstance(leg, LinearLeg):
            provided, leg_coverage = _vector_from_model(leg.greeks_per_unit, leg.quantity_per_unit)
            vector += provided
            coverage += leg_coverage
    return vector, coverage / max(len(candidate.legs), 1), approximation_mismatch


def _expected_physical_positions(
    candidates: tuple[CandidateEconomicPackage, ...],
    positions: tuple[CandidatePosition, ...],
) -> dict[str, float]:
    candidate_map = {candidate.candidate_id: candidate for candidate in candidates}
    expected: dict[str, float] = {}
    for position in positions:
        candidate = candidate_map.get(position.candidate_id)
        if candidate is None:
            raise DualBookReconciliationError(f"unknown candidate position {position.candidate_id}")
        for leg in candidate.legs:
            expected[leg.instrument_id] = (
                expected.get(leg.instrument_id, 0.0) + position.units * leg.quantity_per_unit
            )
    return expected


def _physical_reconciliation_error(
    candidates: tuple[CandidateEconomicPackage, ...],
    positions: tuple[CandidatePosition, ...],
    physical_positions: tuple[PhysicalPosition, ...],
) -> float:
    expected = _expected_physical_positions(candidates, positions)
    actual = {
        position.instrument_id: position.quantity
        for position in physical_positions
        if position.attribution_status == "ATTRIBUTED"
    }
    return float(
        sum(abs(expected.get(key, 0.0) - actual.get(key, 0.0)) for key in set(expected) | set(actual))
    )


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, level: float) -> float:
    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(weights[order])
    index = int(np.searchsorted(cumulative, level, side="left"))
    return float(values[order[min(index, len(values) - 1)]])


def _path_metrics(cube: ScenarioPnLCube) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    scenario_count, step_count, candidate_count = cube.candidate_pnl.shape
    if step_count == 1:
        zeros = np.zeros(candidate_count, dtype=np.float64)
        return zeros, zeros, np.min(cube.candidate_pnl[:, 0, :], axis=0)
    path = np.concatenate([
        np.zeros((scenario_count, 1, candidate_count), dtype=np.float64), cube.candidate_pnl,
    ], axis=1)
    maximum_drawdown = np.max(np.maximum.accumulate(path, axis=1) - path, axis=1)
    worst_step = np.min(np.diff(path, axis=1), axis=(0, 1))
    mean_drawdown = np.sum(maximum_drawdown * cube.probabilities[:, None], axis=0)
    tail_drawdown = np.asarray([
        _weighted_quantile(maximum_drawdown[:, index], cube.probabilities, 0.90)
        for index in range(candidate_count)
    ])
    return mean_drawdown, tail_drawdown, np.asarray(worst_step, dtype=np.float64)


def _greek_matrices(
    candidates: tuple[CandidateEconomicPackage, ...],
    policy: GreekPolicy,
) -> tuple[np.ndarray, np.ndarray, bool]:
    rows = [_candidate_greeks(candidate, policy.approximation_error_max) for candidate in candidates]
    if not rows:
        empty = np.empty((0, len(GREEK_NAMES)))
        return empty, empty.copy(), False
    return np.stack([row[0] for row in rows]), np.stack([row[1] for row in rows]), any(row[2] for row in rows)


def _summary_quality(
    coverage_by_candidate: dict[str, float],
    has_paths: bool,
    approximation_mismatch: bool,
) -> tuple[ComponentQuality, tuple[str, ...]]:
    reasons: list[str] = []
    if any(value < 1.0 for value in coverage_by_candidate.values()):
        reasons.append("GREEK_COVERAGE_INCOMPLETE")
    if approximation_mismatch:
        reasons.append("PROVIDED_GREEKS_MISMATCH_ANALYTIC")
    if not has_paths:
        reasons.append("PATH_EXPOSURE_UNAVAILABLE")
    quality = ComponentQuality.FULLY_QUALIFIED if not reasons else ComponentQuality.DEGRADED
    return quality, tuple(reasons)


def build_greek_path_state(
    cube: ScenarioPnLCube,
    candidates: tuple[CandidateEconomicPackage, ...],
    candidate_positions: tuple[CandidatePosition, ...],
    physical_positions: tuple[PhysicalPosition, ...],
    policy: GreekPolicy,
    require_reconciliation: bool,
) -> tuple[GreekPathArrays, GreekPathSummary]:
    greek_matrix, coverage_matrix, mismatch = _greek_matrices(candidates, policy)
    units = np.asarray([
        {position.candidate_id: position.units for position in candidate_positions}.get(
            candidate.candidate_id, 0.0,
        ) for candidate in candidates
    ])
    portfolio = np.sum(greek_matrix * units[:, None], axis=0) if candidates else np.zeros(len(GREEK_NAMES))
    reconciliation_error = _physical_reconciliation_error(candidates, candidate_positions, physical_positions)
    if require_reconciliation and reconciliation_error > policy.reconciliation_tolerance:
        raise DualBookReconciliationError(
            f"virtual/physical reconciliation error {reconciliation_error} exceeds tolerance"
        )
    mean_drawdown, tail_drawdown, worst_step = _path_metrics(cube)
    coverage_by_candidate = {
        candidate.candidate_id: float(np.mean(coverage_matrix[index]))
        for index, candidate in enumerate(candidates)
    }
    has_paths = len(cube.step_labels) > 1
    quality, reasons = _summary_quality(coverage_by_candidate, has_paths, mismatch)
    arrays = GreekPathArrays(
        candidate_greeks=greek_matrix,
        greek_coverage=coverage_matrix,
        current_portfolio_greeks=portfolio,
        mean_max_drawdown=mean_drawdown,
        tail_max_drawdown=tail_drawdown,
        worst_step_loss=worst_step,
        candidate_ids=tuple(candidate.candidate_id for candidate in candidates),
        greek_names=GREEK_NAMES,
    )
    summary = GreekPathSummary(
        greek_coverage_by_candidate=coverage_by_candidate,
        path_capability_by_candidate={
            candidate.candidate_id: (
                ComponentQuality.FULLY_QUALIFIED if has_paths else ComponentQuality.UNAVAILABLE
            ) for candidate in candidates
        },
        dual_book_reconciliation_error=reconciliation_error,
        quality=quality,
        reason_codes=reasons,
        content_sha256=arrays.content_sha256(),
    )
    return arrays, summary
