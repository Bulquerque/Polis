from __future__ import annotations

import math
from statistics import median


def percentile(values: tuple[float, ...], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def robust_location_scale(values: tuple[float, ...]) -> tuple[float, float]:
    center = median(values)
    q1 = percentile(values, 0.25)
    q3 = percentile(values, 0.75)
    return center, q3 - q1


def average_percentile_rank(value: float, values: tuple[float, ...]) -> float:
    if len(values) == 1:
        return 0.5
    less = sum(item < value for item in values)
    equal = sum(item == value for item in values)
    average_position = less + (equal - 1) / 2.0
    return average_position / (len(values) - 1)


def sigmoid(value: float) -> float:
    bounded = max(-60.0, min(60.0, value))
    return 1.0 / (1.0 + math.exp(-bounded))
