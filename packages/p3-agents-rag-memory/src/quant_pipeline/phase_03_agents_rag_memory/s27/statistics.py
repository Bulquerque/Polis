"""Small dependency-free statistical primitives used by P3.S27."""
from __future__ import annotations

import math
from collections.abc import Sequence

from .errors import S27ContractError


def _validate(values: Sequence[float], weights: Sequence[float]) -> None:
    if len(values) != len(weights) or not values:
        raise S27ContractError("values and weights must be non-empty and aligned")
    if any(weight < 0.0 for weight in weights):
        raise S27ContractError("weights cannot be negative")
    if sum(weights) <= 0.0:
        raise S27ContractError("weights must have positive mass")


def weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    _validate(values, weights)
    total = sum(weights)
    return sum(value * weight for value, weight in zip(values, weights, strict=True)) / total


def weighted_variance(values: Sequence[float], weights: Sequence[float]) -> float:
    mean = weighted_mean(values, weights)
    total = sum(weights)
    return sum(weight * (value - mean) ** 2 for value, weight in zip(values, weights, strict=True)) / total


def weighted_standard_deviation(values: Sequence[float], weights: Sequence[float]) -> float:
    return math.sqrt(max(0.0, weighted_variance(values, weights)))


def effective_sample_size(weights: Sequence[float]) -> float:
    if not weights or any(weight < 0.0 for weight in weights):
        raise S27ContractError("effective sample size requires non-negative weights")
    denominator = sum(weight * weight for weight in weights)
    if denominator <= 0.0:
        return 0.0
    return (sum(weights) ** 2) / denominator


def normalized_entropy(masses: Sequence[float]) -> float:
    positive = [mass for mass in masses if mass > 0.0]
    if len(positive) <= 1:
        return 0.0
    total = sum(positive)
    probabilities = [mass / total for mass in positive]
    entropy = -sum(probability * math.log(probability) for probability in probabilities)
    return entropy / math.log(len(positive))


def hhi(counts: Sequence[int]) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    return sum((count / total) ** 2 for count in counts if count > 0)
