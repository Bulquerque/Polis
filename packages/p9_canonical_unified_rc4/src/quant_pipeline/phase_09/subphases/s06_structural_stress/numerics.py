from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from .contracts import BreachDirection
from .models import QuadraticResponseModel

FloatArray = NDArray[np.float64]


def as_float_array(values: Sequence[float]) -> FloatArray:
    array = np.asarray(values, dtype=np.float64)
    if not np.all(np.isfinite(array)):
        raise ValueError("array contains non-finite values")
    return array


def evaluate_quadratic_response(model: QuadraticResponseModel, shocks: Sequence[float]) -> float:
    vector = as_float_array(shocks)
    linear = as_float_array(model.linear_coefficients)
    quadratic = np.asarray(model.quadratic_matrix, dtype=np.float64)
    if vector.shape != linear.shape:
        raise ValueError("shock vector dimension mismatch")
    return float(model.baseline_value + linear @ vector + 0.5 * vector @ quadratic @ vector)


def weighted_cvar(
    losses: Sequence[float],
    probabilities: Sequence[float],
    confidence: float,
) -> float:
    loss_array = as_float_array(losses)
    probability_array = as_float_array(probabilities)
    if loss_array.shape != probability_array.shape:
        raise ValueError("losses and probabilities must have equal length")
    total = float(np.sum(probability_array))
    if total <= 0:
        raise ValueError("probabilities must sum to a positive value")
    probability_array = probability_array / total
    order = np.argsort(loss_array)[::-1]
    tail_mass = 1.0 - confidence
    remaining = tail_mass
    accumulated = 0.0
    for index in order:
        if remaining <= 1e-15:
            break
        take = min(remaining, float(probability_array[index]))
        accumulated += take * float(loss_array[index])
        remaining -= take
    if remaining > 1e-10:
        raise ValueError("insufficient probability mass for CVaR")
    return accumulated / tail_mass


def lag1_autocorrelation(values: Sequence[float]) -> float:
    array = as_float_array(values)
    if array.size < 3:
        return 0.0
    left = array[:-1] - np.mean(array[:-1])
    right = array[1:] - np.mean(array[1:])
    denominator = math.sqrt(float(left @ left) * float(right @ right))
    return 0.0 if denominator <= 0 else float(left @ right) / denominator


def ewma_scales(values: Sequence[float], decay: float, minimum_scale: float) -> FloatArray:
    array = as_float_array(values)
    variance = np.empty_like(array)
    initial = max(float(np.var(array, ddof=1)), minimum_scale**2)
    variance[0] = initial
    for index in range(1, array.size):
        variance[index] = decay * variance[index - 1] + (1.0 - decay) * array[index - 1] ** 2
    return np.sqrt(np.maximum(variance, minimum_scale**2))


def is_breached(value: float, threshold: float, direction: BreachDirection) -> bool:
    if direction is BreachDirection.LESS_THAN_OR_EQUAL:
        return value <= threshold
    return value >= threshold


def breach_margin(value: float, threshold: float, direction: BreachDirection) -> float:
    if direction is BreachDirection.LESS_THAN_OR_EQUAL:
        return threshold - value
    return value - threshold


def linear_interpolate_zero(x1: float, y1: float, x2: float, y2: float) -> float | None:
    if y1 == 0:
        return x1
    if y2 == 0:
        return x2
    if y1 * y2 > 0 or x1 == x2:
        return None
    weight = -y1 / (y2 - y1)
    return x1 + weight * (x2 - x1)
