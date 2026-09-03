"""CPU-first conditional quantile, heavy-tail and tail-risk marginal models."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.stats import genpareto, gennorm, norm, t

from ..domain.distributions import (
    MixtureComponent,
    MixtureDistribution,
    ParametricDistribution,
    QuantileDistribution,
    QuantilePoint,
    quantile_value,
)
from ..errors import DataQualityError

_LEVELS = (0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99)
_EPS = 1e-12


def conditional_quantiles(values: np.ndarray) -> tuple[QuantileDistribution, dict[str, Any]]:
    array = _validated(values, minimum=30)
    forecasts: list[float] = []
    diagnostics: list[dict[str, Any]] = []
    for level in _LEVELS:
        empirical = _weighted_quantile(array, level)
        caviar, fitted = _caviar_forecast(array, level)
        regime = _regime_quantile(array, level)
        candidate = 0.60 * caviar + 0.25 * regime + 0.15 * empirical
        forecasts.append(float(candidate))
        diagnostics.append({
            "level": level,
            "empirical": empirical,
            "caviar": caviar,
            "regime_conditioned": regime,
            "caviar_parameters": fitted,
        })
    monotonic = np.maximum.accumulate(np.asarray(forecasts, dtype=float))
    crossing_before = int(np.sum(np.diff(forecasts) < 0.0))
    distribution = QuantileDistribution(quantiles=tuple(
        QuantilePoint(level=level, value=float(value))
        for level, value in zip(_LEVELS, monotonic, strict=True)
    ))
    return distribution, {
        "method": "CAVIAR_SAV_REGIME_BLEND_WITH_EMPIRICAL_BASELINE",
        "non_crossing_method": "MONOTONE_REARRANGEMENT",
        "crossing_count_before_repair": crossing_before,
        "non_crossing_enforced": True,
        "effective_sample_size": _effective_recency_sample(len(array)),
        "levels": diagnostics,
    }


def heavy_tail_candidates(
    values: np.ndarray,
) -> tuple[tuple[str, ParametricDistribution | MixtureDistribution, dict[str, Any]], ...]:
    array = _validated(values, minimum=30)
    split = max(20, int(len(array) * 0.80))
    train, validation = array[:split], array[split:]
    if len(validation) < 5:
        train, validation = array[:-5], array[-5:]
    candidates = (
        ("student-t", _student_t(train)),
        ("ged", _ged(train)),
        ("two-component-normal-mixture", _normal_mixture(train)),
    )
    output = []
    scores = []
    for name, distribution in candidates:
        log_score = _negative_log_score(distribution, validation)
        crps_proxy = _crps_quantile_proxy(distribution, validation)
        combined = log_score + crps_proxy
        scores.append((combined, name))
        output.append((name, distribution, {
            "validation_log_score": log_score,
            "validation_crps_proxy": crps_proxy,
            "combined_proper_score": combined,
            "training_sample_size": len(train),
            "validation_sample_size": len(validation),
        }))
    champion = min(scores)[1]
    return tuple((name, distribution, {
        **metadata,
        "candidate_status": (
            "CHAMPION_CANDIDATE" if name == champion else "QUALIFIED_CHALLENGER_CANDIDATE"
        ),
        "selected_by_holdout_score": name == champion,
    }) for name, distribution, metadata in output)


def evt_diagnostics(values: np.ndarray, level: float = 0.95) -> dict[str, Any]:
    array = _validated(values, minimum=40)
    losses = np.maximum(-array, 0.0)
    positive = losses[losses > 0.0]
    fits = [_fit_threshold(positive, threshold) for threshold in (0.75, 0.80, 0.85)]
    stable = [row for row in fits if row is not None]
    if not stable:
        return _empirical_tail(losses, level)
    selected = min(stable, key=lambda row: abs(row["quantile"] - 0.80))
    var, expected_shortfall = _gpd_risk(selected, len(losses), level)
    interval = _tail_bootstrap_interval(losses, level)
    violations = losses > var
    violation_rate = float(np.mean(violations))
    independence = _violation_independence(violations)
    tail_mean = float(np.mean(losses[violations])) if np.any(violations) else var
    return {
        **selected,
        "var": var,
        "expected_shortfall": max(expected_shortfall, var),
        "confidence_level": level,
        "threshold_stability_shape_std": float(np.std([row["shape"] for row in stable])),
        "threshold_stability_scale_cv": _coefficient_of_variation([row["scale"] for row in stable]),
        "var_bootstrap_ci": interval,
        "var_violation_rate": violation_rate,
        "var_coverage_error": abs(violation_rate - (1.0 - level)),
        "violation_independence_lag1": independence,
        "es_backtest_tail_mean": tail_mean,
        "es_backtest_error": float(tail_mean - expected_shortfall),
        "method": "POT_GPD_THRESHOLD_STABILITY_BOOTSTRAP",
    }


def _validated(values: np.ndarray, minimum: int) -> np.ndarray:
    array = np.asarray(values, dtype=float).reshape(-1)
    if len(array) < minimum or not np.all(np.isfinite(array)):
        raise DataQualityError(f"marginal model requires {minimum} finite observations")
    return array


def _weighted_quantile(array: np.ndarray, level: float) -> float:
    weights = np.geomspace(0.25, 1.0, len(array))
    weights /= weights.sum()
    order = np.argsort(array)
    cumulative = np.cumsum(weights[order])
    index = min(int(np.searchsorted(cumulative, level)), len(array) - 1)
    return float(array[order][index])


def _effective_recency_sample(length: int) -> float:
    weights = np.geomspace(0.25, 1.0, length)
    weights /= weights.sum()
    return float(1.0 / np.sum(weights**2))


def _caviar_forecast(array: np.ndarray, level: float) -> tuple[float, dict[str, float]]:
    initial = float(np.quantile(array, level))
    scale = max(float(np.std(array, ddof=1)), 1e-6)
    start = np.asarray([initial * 0.1, 0.1, 0.85], dtype=float)
    bounds = [(-5.0 * scale, 5.0 * scale), (0.0, 2.0), (0.0, 0.995)]
    result = minimize(
        _caviar_objective,
        start,
        args=(array, level, initial),
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 80, "ftol": 1e-9},
    )
    parameters = result.x if result.success else start
    path = _caviar_path(array, parameters, initial)
    forecast = parameters[0] + parameters[1] * abs(array[-1]) + parameters[2] * path[-1]
    return float(forecast), {
        "intercept": float(parameters[0]),
        "absolute_return": float(parameters[1]),
        "persistence": float(parameters[2]),
        "converged": bool(result.success),
    }


def _caviar_objective(
    parameters: np.ndarray, array: np.ndarray, level: float, initial: float,
) -> float:
    path = _caviar_path(array, parameters, initial)
    errors = array[1:] - path[1:]
    loss = np.maximum(level * errors, (level - 1.0) * errors)
    return float(np.mean(loss))


def _caviar_path(array: np.ndarray, parameters: np.ndarray, initial: float) -> np.ndarray:
    path = np.empty_like(array)
    path[0] = initial
    for index in range(1, len(array)):
        path[index] = (
            parameters[0]
            + parameters[1] * abs(array[index - 1])
            + parameters[2] * path[index - 1]
        )
    return path


def _regime_quantile(array: np.ndarray, level: float) -> float:
    volatility = np.abs(array)
    threshold = float(np.median(volatility))
    current_high = volatility[-1] >= threshold
    selected = array[volatility >= threshold] if current_high else array[volatility < threshold]
    if len(selected) < 8:
        selected = array
    return float(np.quantile(selected, level))


def _student_t(array: np.ndarray) -> ParametricDistribution:
    degrees, location, scale = t.fit(array)
    return ParametricDistribution(
        family="STUDENT_T",
        location=float(location),
        scale=max(float(scale), _EPS),
        degrees_of_freedom=max(float(degrees), 2.01),
    )


def _ged(array: np.ndarray) -> ParametricDistribution:
    shape, location, scale = gennorm.fit(array)
    return ParametricDistribution(
        family="GED",
        location=float(location),
        scale=max(float(scale), _EPS),
        shape_parameter=max(float(shape), 0.20),
    )


def _normal_mixture(array: np.ndarray) -> MixtureDistribution:
    means = np.quantile(array, [0.25, 0.75]).astype(float)
    scales = np.full(2, max(float(np.std(array, ddof=1)), _EPS), dtype=float)
    weights = np.asarray([0.5, 0.5], dtype=float)
    for _ in range(24):
        density = np.column_stack([
            weights[index] * norm.pdf(array, loc=means[index], scale=max(scales[index], _EPS))
            for index in range(2)
        ])
        responsibility = density / np.maximum(density.sum(axis=1, keepdims=True), _EPS)
        totals = responsibility.sum(axis=0)
        weights = totals / len(array)
        means = (responsibility * array[:, None]).sum(axis=0) / np.maximum(totals, _EPS)
        variances = (
            responsibility * (array[:, None] - means[None, :]) ** 2
        ).sum(axis=0) / np.maximum(totals, _EPS)
        scales = np.sqrt(np.maximum(variances, _EPS))
    weights /= weights.sum()
    return MixtureDistribution(components=tuple(
        MixtureComponent(
            family="NORMAL",
            weight=float(weights[index]),
            location=float(means[index]),
            scale=float(scales[index]),
        )
        for index in range(2)
    ))


def _negative_log_score(distribution, values: np.ndarray) -> float:
    density = np.asarray([_density(distribution, value) for value in values], dtype=float)
    return float(-np.mean(np.log(np.maximum(density, _EPS))))


def _density(distribution, value: float) -> float:
    if isinstance(distribution, ParametricDistribution):
        if distribution.family == "STUDENT_T":
            return float(t.pdf(value, distribution.degrees_of_freedom, distribution.location, distribution.scale))
        if distribution.family == "GED":
            return float(gennorm.pdf(value, distribution.shape_parameter, distribution.location, distribution.scale))
        return float(norm.pdf(value, distribution.location, distribution.scale))
    return float(sum(
        item.weight * norm.pdf(value, item.location, item.scale)
        for item in distribution.components
    ))


def _crps_quantile_proxy(distribution, values: np.ndarray) -> float:
    levels = np.linspace(0.05, 0.95, 19)
    quantiles = np.asarray([quantile_value(distribution, float(level)) for level in levels])
    losses = []
    for value in values:
        errors = value - quantiles
        losses.append(np.mean(np.maximum(levels * errors, (levels - 1.0) * errors)))
    return float(2.0 * np.mean(losses))


def _fit_threshold(positive: np.ndarray, quantile: float) -> dict[str, Any] | None:
    if len(positive) < 10:
        return None
    threshold = float(np.quantile(positive, quantile))
    excess = positive[positive > threshold] - threshold
    if len(excess) < 6:
        return None
    shape, _, scale = genpareto.fit(excess, floc=0.0)
    return {
        "quantile": quantile,
        "threshold": threshold,
        "shape": float(shape),
        "scale": max(float(scale), _EPS),
        "exceedance_count": len(excess),
        "tail_fraction": float(len(excess) / len(positive)),
    }


def _gpd_risk(fit: dict[str, Any], total_count: int, level: float) -> tuple[float, float]:
    tail_fraction = fit["exceedance_count"] / total_count
    ratio = max(tail_fraction / (1.0 - level), 1.0)
    shape, scale, threshold = fit["shape"], fit["scale"], fit["threshold"]
    if abs(shape) < 1e-8:
        var = threshold + scale * math.log(ratio)
        expected_shortfall = var + scale
    else:
        var = threshold + scale / shape * (ratio**shape - 1.0)
        expected_shortfall = (var + scale - shape * threshold) / max(1.0 - shape, _EPS)
    return max(float(var), 0.0), max(float(expected_shortfall), 0.0)


def _tail_bootstrap_interval(losses: np.ndarray, level: float) -> tuple[float, float]:
    generator = np.random.default_rng(0)
    estimates = [
        float(np.quantile(generator.choice(losses, size=len(losses), replace=True), level))
        for _ in range(64)
    ]
    return float(np.quantile(estimates, 0.025)), float(np.quantile(estimates, 0.975))


def _violation_independence(violations: np.ndarray) -> float:
    if len(violations) < 3 or np.std(violations[:-1]) == 0.0 or np.std(violations[1:]) == 0.0:
        return 0.0
    return float(np.corrcoef(violations[:-1].astype(float), violations[1:].astype(float))[0, 1])


def _coefficient_of_variation(values: list[float]) -> float:
    mean = max(abs(float(np.mean(values))), _EPS)
    return float(np.std(values, ddof=0) / mean)


def _empirical_tail(losses: np.ndarray, level: float) -> dict[str, Any]:
    var = max(float(np.quantile(losses, level)), 0.0)
    tail = losses[losses >= var]
    expected_shortfall = max(float(np.mean(tail)) if len(tail) else var, var)
    return {
        "threshold": 0.0,
        "shape": 0.0,
        "scale": 0.0,
        "var": var,
        "expected_shortfall": expected_shortfall,
        "confidence_level": level,
        "exceedance_count": len(tail),
        "tail_fraction": float(len(tail) / len(losses)),
        "var_bootstrap_ci": _tail_bootstrap_interval(losses, level),
        "method": "EMPIRICAL_POSITIVE_LOSS_FALLBACK",
    }
