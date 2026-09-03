"""CPU-first volatility, tail and scenario estimators."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.stats import genpareto, norm, t

from ..domain.distributions import (
    EmpiricalDistribution,
    ParametricDistribution,
    QuantileDistribution,
    QuantilePoint,
    ScenarioDistribution,
    ScenarioPoint,
)
from ..errors import DataQualityError

EPS = 1e-12


def validate_returns(values: np.ndarray, *, minimum: int = 2) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or len(array) < minimum or not np.all(np.isfinite(array)):
        raise DataQualityError(f"return series requires at least {minimum} finite observations")
    if np.any(array < -1.0):
        raise DataQualityError("simple returns cannot be below -100%")
    return array


def ewma_variance(values: np.ndarray, decay: float = 0.94) -> float:
    array = validate_returns(values, minimum=2)
    if not 0.0 < decay < 1.0:
        raise DataQualityError("EWMA requires valid decay")
    variance = float(array[0] ** 2)
    for value in array[1:]:
        variance = decay * variance + (1.0 - decay) * float(value**2)
    return max(variance, EPS)


def har_variance(values: np.ndarray) -> tuple[float, dict[str, float | str]]:
    array = validate_returns(values, minimum=2)
    if len(array) < 24:
        return ewma_variance(array), {"method": "EWMA_FALLBACK", "sample_size": float(len(array))}
    squared = np.maximum(array**2, EPS)
    design, response = _har_design(squared)
    penalty = np.eye(design.shape[1]) * 1e-6
    penalty[0, 0] = 0.0
    coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ response)
    latest = np.asarray([
        1.0, math.log(squared[-1]),
        math.log(float(np.mean(squared[-5:]))),
        math.log(float(np.mean(squared[-22:]))),
    ])
    prediction = max(float(math.exp(float(latest @ coefficients))), EPS)
    return prediction, {
        "method": "LOG_HAR", "daily_beta": float(coefficients[1]),
        "weekly_beta": float(coefficients[2]), "monthly_beta": float(coefficients[3]),
    }


def _har_design(squared: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rows, targets = [], []
    for index in range(22, len(squared)):
        rows.append([
            1.0, math.log(squared[index - 1]),
            math.log(float(np.mean(squared[index - 5:index]))),
            math.log(float(np.mean(squared[index - 22:index]))),
        ])
        targets.append(math.log(squared[index]))
    return np.asarray(rows, dtype=float), np.asarray(targets, dtype=float)


def gjr_variance(values: np.ndarray) -> tuple[float, dict[str, Any]]:
    """Estimate bounded GJR-GARCH under Gaussian and Student-t innovations."""
    array = validate_returns(values, minimum=20)
    unconditional = max(float(np.var(array, ddof=1)), EPS)
    best: tuple[float, float, float, float, float, str, float | None] | None = None
    for alpha in (0.03, 0.06, 0.10, 0.14):
        for gamma in (0.0, 0.04, 0.08, 0.12):
            for beta in (0.72, 0.80, 0.86, 0.92):
                persistence = alpha + 0.5 * gamma + beta
                if persistence >= 0.995:
                    continue
                omega = unconditional * max(1.0 - persistence, 1e-4)
                for family, degrees in _innovation_candidates():
                    likelihood, variance = _gjr_likelihood(
                        array, omega, alpha, gamma, beta, unconditional, family, degrees,
                    )
                    candidate = (likelihood, alpha, gamma, beta, variance, family, degrees)
                    if best is None or candidate[0] < best[0]:
                        best = candidate
    if best is None:
        raise DataQualityError("GJR parameter estimation found no stationary candidate")
    likelihood, alpha, gamma, beta, variance, family, degrees = best
    last = float(array[-1])
    omega = unconditional * max(1.0 - alpha - 0.5 * gamma - beta, 1e-4)
    forecast = omega + alpha * last**2 + (gamma * last**2 if last < 0.0 else 0.0) + beta * variance
    uncertainty = forecast * math.sqrt(2.0 / max(len(array) - 1, 1))
    return max(float(forecast), EPS), {
        "method": "GJR_GARCH_GRID_MLE",
        "search_policy": "BOUNDED_GRID",
        "alpha": alpha, "gamma": gamma, "beta": beta,
        "stationary": True, "convergence_status": "GRID_OPTIMUM_FOUND",
        "innovation_family": family, "degrees_of_freedom": degrees,
        "negative_log_likelihood": float(likelihood),
        "forecast_standard_error_proxy": float(uncertainty),
        "parameter_bounds_version": "P5-RC34-GJR-V2",
    }


def _innovation_candidates() -> tuple[tuple[str, float | None], ...]:
    return (("GAUSSIAN", None), ("STUDENT_T", 5.0), ("STUDENT_T", 8.0), ("STUDENT_T", 12.0))


def _gjr_likelihood(values, omega, alpha, gamma, beta, initial, family, degrees):
    variance = initial
    objective = 0.0
    for lag, value in zip(values[:-1], values[1:], strict=True):
        variance = omega + alpha * lag**2 + (gamma * lag**2 if lag < 0.0 else 0.0) + beta * variance
        variance = max(float(variance), EPS)
        standardized = float(value) / math.sqrt(variance)
        log_density = (
            norm.logpdf(standardized)
            if family == "GAUSSIAN"
            else t.logpdf(standardized, df=degrees)
        )
        objective -= float(log_density - 0.5 * math.log(variance))
    return objective, variance


def implied_blend(realized_variance: float, option_state: dict[str, Any]) -> tuple[float, dict[str, float | str]]:
    implied = option_state.get("implied_volatility") or option_state.get("iv_atm")
    coverage = option_state.get("coverage")
    if implied is None or not np.isfinite(float(implied)) or float(implied) <= 0.0:
        raise DataQualityError("option-implied forecast requires positive finite IV")
    if coverage is None or not np.isfinite(float(coverage)) or not 0.0 < float(coverage) <= 1.0:
        raise DataQualityError("option coverage must be explicitly available in (0, 1]")
    weight = float(coverage)
    blended = (1.0 - weight) * realized_variance + weight * float(implied) ** 2
    return max(blended, EPS), {"method": "REALIZED_IMPLIED_BLEND", "implied_weight": weight}


def path_risk(values: np.ndarray, liquidity: np.ndarray | None = None) -> dict[str, float]:
    array = validate_returns(values, minimum=8)
    downside = array[array < 0.0]
    downside_variance = float(np.mean(downside**2)) if len(downside) else 0.0
    cumulative = np.cumprod(1.0 + array)
    peaks = np.maximum.accumulate(cumulative)
    drawdowns = 1.0 - cumulative / np.maximum(peaks, EPS)
    scale = max(float(np.std(array, ddof=1)), EPS)
    output = {
        "downside_volatility": math.sqrt(max(downside_variance, 0.0)),
        "maximum_drawdown": float(np.max(drawdowns)),
        "jump_probability": float(np.mean(np.abs(array) > 3.0 * scale)),
        "path_minimum": float(np.min(cumulative) - 1.0),
        "path_maximum": float(np.max(cumulative) - 1.0),
    }
    if liquidity is not None:
        series = np.asarray(liquidity, dtype=float)
        if len(series) and np.all(np.isfinite(series)):
            output["liquidity_risk"] = float(np.quantile(np.maximum(series, 0.0), 0.95))
    return output


def empirical_quantiles(
    values: np.ndarray,
    levels: tuple[float, ...] = (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99),
) -> QuantileDistribution:
    array = validate_returns(values, minimum=8)
    points = tuple(QuantilePoint(level=level, value=float(np.quantile(array, level))) for level in levels)
    return QuantileDistribution(quantiles=points)


def dynamic_quantiles(values: np.ndarray) -> tuple[QuantileDistribution, dict[str, Any]]:
    """Recency-weighted empirical conditional quantile baseline."""
    array = validate_returns(values, minimum=12)
    weights = np.geomspace(0.25, 1.0, len(array))
    weights /= weights.sum()
    levels = (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)
    order = np.argsort(array)
    sorted_values, cumulative = array[order], np.cumsum(weights[order])
    points = tuple(
        QuantilePoint(level=level, value=float(sorted_values[min(np.searchsorted(cumulative, level), len(array) - 1)]))
        for level in levels
    )
    return QuantileDistribution(quantiles=points), {
        "method": "RECENCY_WEIGHTED_EMPIRICAL_QUANTILES", "effective_sample_size": float(1.0 / np.sum(weights**2)),
    }


def evt_tail(values: np.ndarray, level: float = 0.95) -> dict[str, float | str]:
    array = validate_returns(values, minimum=30)
    losses = np.maximum(-array, 0.0)
    positive = losses[losses > 0.0]
    if len(positive) < 5:
        return _empirical_tail(losses, level)
    threshold = float(np.quantile(positive, 0.80))
    excess = positive[positive > threshold] - threshold
    if len(excess) < 5:
        return _empirical_tail(losses, level)
    shape, _, scale = genpareto.fit(excess, floc=0.0)
    scale = max(float(scale), EPS)
    tail_fraction, probability = len(excess) / len(losses), 1.0 - level
    ratio = max(tail_fraction / probability, 1.0)
    var = threshold + (scale * math.log(ratio) if abs(shape) < 1e-8 else scale / shape * (ratio**shape - 1.0))
    expected_shortfall = var + scale if abs(shape) < 1e-8 else (var + scale - shape * threshold) / max(1.0 - shape, EPS)
    var = max(float(var), 0.0)
    expected_shortfall = max(float(expected_shortfall), var)
    return {
        "threshold": threshold, "shape": float(shape), "scale": scale, "var": var,
        "expected_shortfall": expected_shortfall, "confidence_level": level,
        "exceedance_count": float(len(excess)), "tail_fraction": float(tail_fraction),
        "method": "POT_GPD_POSITIVE_LOSS",
    }


def _empirical_tail(losses: np.ndarray, level: float) -> dict[str, float | str]:
    var = max(float(np.quantile(losses, level)), 0.0)
    tail = losses[losses >= var]
    expected_shortfall = max(float(np.mean(tail)) if len(tail) else var, var)
    return {
        "threshold": 0.0, "shape": 0.0, "scale": 0.0, "var": var,
        "expected_shortfall": expected_shortfall, "confidence_level": level,
        "exceedance_count": float(len(tail)), "tail_fraction": float(len(tail) / len(losses)),
        "method": "EMPIRICAL_POSITIVE_LOSS_FALLBACK",
    }


def student_t_distribution(values: np.ndarray) -> ParametricDistribution:
    array = validate_returns(values, minimum=12)
    degrees, location, scale = t.fit(array)
    return ParametricDistribution(
        family="STUDENT_T", location=float(location), scale=max(float(scale), EPS),
        degrees_of_freedom=max(float(degrees), 2.01),
    )


def bootstrap_scenarios(values: np.ndarray, *, seed: int, count: int = 64, block: int = 5) -> EmpiricalDistribution:
    """Stationary block bootstrap aggregated into multi-session returns."""
    array = validate_returns(values, minimum=block * 2)
    if count < 2 or block < 1:
        raise DataQualityError("scenario bootstrap count and block must be positive")
    generator = np.random.default_rng(seed)
    samples = []
    restart_probability = 1.0 / block
    for _ in range(count):
        index = int(generator.integers(0, len(array)))
        path = []
        for _step in range(block):
            path.append(array[index])
            index = int(generator.integers(0, len(array))) if generator.random() < restart_probability else (index + 1) % len(array)
        samples.append(float(np.prod(1.0 + np.asarray(path)) - 1.0))
    return EmpiricalDistribution(samples=tuple(samples))


def compressed_scenarios(distribution: EmpiricalDistribution) -> ScenarioDistribution:
    levels, probabilities = (0.05, 0.25, 0.50, 0.75, 0.95), (0.10, 0.20, 0.40, 0.20, 0.10)
    scenarios = tuple(
        ScenarioPoint(scenario_id=f"scenario-{index + 1}", value=float(np.quantile(distribution.samples, level)), probability=probability)
        for index, (level, probability) in enumerate(zip(levels, probabilities, strict=True))
    )
    return ScenarioDistribution(scenarios=scenarios)


def validate_distribution_set(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise DataQualityError("tail/scenario validation requires records")
    failures, scenario_vectors = [], []
    for row in records:
        distribution = row.get("distribution", {})
        if row.get("unit") == "positive_loss" and distribution.get("kind") == "POINT":
            if distribution.get("value") is None:
                failures.append({"record_id": row.get("record_id"), "reason": "POINT_VALUE_UNAVAILABLE"})
            elif float(distribution["value"]) < 0.0:
                failures.append({"record_id": row.get("record_id"), "reason": "NEGATIVE_POSITIVE_LOSS"})
        if distribution.get("kind") == "SCENARIOS":
            probabilities = [float(item["probability"]) for item in distribution.get("scenarios", [])]
            values = [float(item["value"]) for item in distribution.get("scenarios", [])]
            if not probabilities or abs(sum(probabilities) - 1.0) > 1e-8:
                failures.append({"record_id": row.get("record_id"), "reason": "INVALID_SCENARIO_MASS"})
            if len(set(values)) < min(3, len(values)):
                failures.append({"record_id": row.get("record_id"), "reason": "SCENARIO_COLLAPSE"})
            scenario_vectors.extend(values)
    effective = 0.0
    if scenario_vectors:
        _, counts = np.unique(np.round(scenario_vectors, 12), return_counts=True)
        probabilities = counts / counts.sum()
        effective = float(np.exp(-np.sum(probabilities * np.log(probabilities))))
    return {
        "passed": not failures, "failures": failures, "record_count": len(records),
        "effective_scenario_count": effective,
    }
