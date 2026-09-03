"""Small deterministic statistical primitives for P3.S28."""
from __future__ import annotations

from math import sqrt
from collections.abc import Sequence

from .errors import S28ContractError


def weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    if len(values) != len(weights) or not values:
        raise S28ContractError("weighted_mean requires equal non-empty sequences")
    total = sum(weights)
    if total <= 0.0:
        raise S28ContractError("weighted_mean requires positive total weight")
    return sum(value * weight for value, weight in zip(values, weights, strict=True)) / total


def weighted_variance(values: Sequence[float], weights: Sequence[float], mean: float | None = None) -> float:
    if mean is None:
        mean = weighted_mean(values, weights)
    total = sum(weights)
    if total <= 0.0:
        raise S28ContractError("weighted_variance requires positive total weight")
    return sum(weight * (value - mean) ** 2 for value, weight in zip(values, weights, strict=True)) / total


def weighted_population_std(values: Sequence[float], weights: Sequence[float]) -> float:
    return sqrt(max(0.0, weighted_variance(values, weights)))


def effective_sample_size(weights: Sequence[float]) -> float:
    positive = [weight for weight in weights if weight > 0.0]
    if not positive:
        return 0.0
    numerator = sum(positive) ** 2
    denominator = sum(weight * weight for weight in positive)
    return numerator / denominator


def weighted_fraction(flags: Sequence[bool], weights: Sequence[float]) -> float:
    if len(flags) != len(weights) or not flags:
        raise S28ContractError("weighted_fraction requires equal non-empty sequences")
    total = sum(weights)
    if total <= 0.0:
        return 0.0
    return sum(weight for flag, weight in zip(flags, weights, strict=True) if flag) / total


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return min(upper, max(lower, value))
