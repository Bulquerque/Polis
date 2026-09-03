from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
from numpy.typing import NDArray
from scipy.stats import chi2

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]


def to_float_matrix(values: tuple[tuple[float, ...], ...]) -> FloatArray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 2 or not np.isfinite(array).all():
        raise ValueError("expected a finite two-dimensional array")
    return array


def autocovariance(values: FloatArray, lag: int) -> float:
    if lag < 0 or lag >= values.size:
        raise ValueError("lag outside valid range")
    centered = values - values.mean()
    return float(centered[lag:] @ centered[: values.size - lag] / values.size)


def autocorrelation(values: FloatArray, maximum_lag: int) -> FloatArray:
    centered = values - values.mean()
    denominator = float(centered @ centered)
    lags = min(maximum_lag, values.size - 1)
    result = np.empty(lags + 1, dtype=np.float64)
    result[0] = 1.0
    if denominator <= np.finfo(np.float64).eps:
        result[1:] = 0.0
        return result
    for lag in range(1, lags + 1):
        result[lag] = float(centered[lag:] @ centered[:-lag] / denominator)
    return result


def ljung_box(values: FloatArray, lag: int) -> tuple[float, float]:
    nobs = values.size
    selected_lag = min(lag, nobs - 1)
    if selected_lag < 1:
        return 0.0, 1.0
    acf = autocorrelation(values, selected_lag)[1:]
    denominators = nobs - np.arange(1, selected_lag + 1, dtype=np.float64)
    statistic = float(nobs * (nobs + 2) * np.sum((acf * acf) / denominators))
    pvalue = float(chi2.sf(statistic, selected_lag))
    return statistic, pvalue


def effective_sample_size(values: FloatArray, maximum_lag: int) -> float:
    nobs = values.size
    acf = autocorrelation(values, min(maximum_lag, nobs - 1))[1:]
    positive_sum = 0.0
    for rho in acf:
        if rho <= 0:
            break
        positive_sum += float(rho)
    denominator = 1.0 + 2.0 * positive_sum
    return float(np.clip(nobs / denominator, 1.0, float(nobs)))


def dependence_horizon(values: FloatArray, maximum_lag: int) -> int:
    nobs = values.size
    acf = autocorrelation(values, min(maximum_lag, nobs - 1))[1:]
    if acf.size == 0:
        return 1
    band = 2.0 * math.sqrt(max(math.log10(max(nobs, 10)), 1.0) / nobs)
    significant = np.flatnonzero(np.abs(acf) >= band)
    return int(significant[-1] + 1) if significant.size else 1


def stable_correlation(matrix: FloatArray) -> FloatArray:
    if matrix.shape[1] == 1:
        return np.ones((1, 1), dtype=np.float64)
    standard_deviation = matrix.std(axis=0, ddof=1)
    active = standard_deviation > np.finfo(np.float64).eps
    result = np.eye(matrix.shape[1], dtype=np.float64)
    if active.sum() >= 2:
        active_corr = np.corrcoef(matrix[:, active], rowvar=False)
        result[np.ix_(active, active)] = active_corr
    return result


def off_diagonal_absolute_mean(matrix: FloatArray) -> float:
    if matrix.shape[0] < 2:
        return 0.0
    mask = ~np.eye(matrix.shape[0], dtype=bool)
    return float(np.mean(np.abs(matrix[mask])))


def maximum_drawdown(returns: FloatArray) -> float:
    wealth = np.cumprod(1.0 + returns)
    running_max = np.maximum.accumulate(np.concatenate(([1.0], wealth)))
    wealth_with_initial = np.concatenate(([1.0], wealth))
    drawdown = wealth_with_initial / running_max - 1.0
    return float(np.min(drawdown))


def hhi(values: Iterable[float]) -> float:
    array = np.abs(np.asarray(tuple(values), dtype=np.float64))
    total = float(array.sum())
    if total <= np.finfo(np.float64).eps:
        return 0.0
    shares = array / total
    return float(shares @ shares)
