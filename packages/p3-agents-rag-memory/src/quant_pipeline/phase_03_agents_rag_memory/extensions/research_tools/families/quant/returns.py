"""Return statistics with explicit conventions and no adaptive window selection."""
from __future__ import annotations

import statistics
from collections.abc import Sequence

from .model_base import QuantMode
from .ports import QuantDataError
from .series import median_absolute_deviation, quantile, sample_std, trimmed_mean


def return_statistics(
    values: Sequence[float],
    *,
    mode: QuantMode,
    quantiles: Sequence[float],
    trim_fraction: float,
    annualization_factor: float,
) -> tuple[dict[str, float | int | dict[str, float]], tuple[str, ...]]:
    if not values:
        raise QuantDataError("return statistics require at least one return")
    metrics: dict[str, float | int | dict[str, float]] = {
        "observation_count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
        "quantiles": {str(probability): quantile(values, probability) for probability in quantiles},
    }
    diagnostics: list[str] = ["sample_std_uses_ddof_1"]
    if len(values) >= 2:
        standard_deviation = sample_std(values)
        metrics["sample_standard_deviation"] = standard_deviation
        metrics["annualized_standard_deviation"] = standard_deviation * annualization_factor**0.5
    else:
        diagnostics.append("sample_standard_deviation_unavailable")
    if mode in {QuantMode.ROBUST, QuantMode.STABILITY}:
        metrics["trimmed_mean"] = trimmed_mean(values, trim_fraction)
        metrics["median_absolute_deviation"] = median_absolute_deviation(values)
    return metrics, tuple(diagnostics)
