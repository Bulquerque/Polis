"""Pearson and Spearman dependence diagnostics with explicit alignment."""
from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

from .model_base import CorrelationMethod
from .ports import QuantDataError
from .series import average_ranks


def pearson_correlation(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise QuantDataError("correlation series must have equal length")
    if len(left) < 2:
        raise QuantDataError("correlation requires at least two observations")
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    left_centered = [value - left_mean for value in left]
    right_centered = [value - right_mean for value in right]
    left_norm = math.sqrt(sum(value * value for value in left_centered))
    right_norm = math.sqrt(sum(value * value for value in right_centered))
    if left_norm == 0.0 or right_norm == 0.0:
        raise QuantDataError("correlation is undefined for a constant series")
    return sum(a * b for a, b in zip(left_centered, right_centered, strict=True)) / (left_norm * right_norm)


def spearman_correlation(left: Sequence[float], right: Sequence[float]) -> float:
    return pearson_correlation(average_ranks(left), average_ranks(right))


def correlation_value(
    method: CorrelationMethod,
    left: Sequence[float],
    right: Sequence[float],
) -> float:
    if method is CorrelationMethod.PEARSON:
        return pearson_correlation(left, right)
    if method is CorrelationMethod.SPEARMAN:
        return spearman_correlation(left, right)
    raise QuantDataError(f"unsupported correlation method: {method}")
