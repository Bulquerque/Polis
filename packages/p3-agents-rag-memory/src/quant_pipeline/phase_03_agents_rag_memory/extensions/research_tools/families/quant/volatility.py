"""Close-to-close, Parkinson and Garman-Klass volatility estimators."""
from __future__ import annotations

import math
from collections.abc import Sequence

from .model_base import VolatilityEstimator
from .ports import QuantDataError
from .series import MarketBar, compute_returns, sample_std
from .model_base import ReturnKind


def close_to_close_volatility(bars: Sequence[MarketBar], annualization_factor: float) -> float:
    returns = [point.value for point in compute_returns(bars, ReturnKind.LOG)]
    return sample_std(returns) * math.sqrt(annualization_factor)


def parkinson_volatility(bars: Sequence[MarketBar], annualization_factor: float) -> float:
    variances: list[float] = []
    for bar in bars:
        if bar.high is None or bar.low is None:
            raise QuantDataError("Parkinson estimator requires high and low for every bar")
        log_range = math.log(bar.high / bar.low)
        variances.append((log_range * log_range) / (4.0 * math.log(2.0)))
    if not variances:
        raise QuantDataError("Parkinson estimator requires bars")
    return math.sqrt(sum(variances) / len(variances) * annualization_factor)


def garman_klass_volatility(bars: Sequence[MarketBar], annualization_factor: float) -> float:
    variances: list[float] = []
    coefficient = 2.0 * math.log(2.0) - 1.0
    for bar in bars:
        if bar.open is None or bar.high is None or bar.low is None:
            raise QuantDataError("Garman-Klass estimator requires open, high and low for every bar")
        log_range = math.log(bar.high / bar.low)
        log_close_open = math.log(bar.close / bar.open)
        variances.append(0.5 * log_range * log_range - coefficient * log_close_open * log_close_open)
    if not variances:
        raise QuantDataError("Garman-Klass estimator requires bars")
    mean_variance = sum(variances) / len(variances)
    if mean_variance < 0.0:
        raise QuantDataError("Garman-Klass mean variance is negative for the supplied bars")
    return math.sqrt(mean_variance * annualization_factor)


def estimator_value(
    estimator: VolatilityEstimator,
    bars: Sequence[MarketBar],
    annualization_factor: float,
) -> float:
    if estimator is VolatilityEstimator.CLOSE_TO_CLOSE:
        return close_to_close_volatility(bars, annualization_factor)
    if estimator is VolatilityEstimator.PARKINSON:
        return parkinson_volatility(bars, annualization_factor)
    if estimator is VolatilityEstimator.GARMAN_KLASS:
        return garman_klass_volatility(bars, annualization_factor)
    raise QuantDataError(f"unsupported estimator: {estimator}")
