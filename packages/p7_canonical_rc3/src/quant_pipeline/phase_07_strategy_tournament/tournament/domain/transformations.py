from __future__ import annotations

import math

from .enums import NormalizationMethod, TransformationMethod
from .statistics import average_percentile_rank, robust_location_scale, sigmoid


def transform_value(value: float, method: TransformationMethod, lower: float | None, upper: float | None) -> float:
    if method == TransformationMethod.IDENTITY:
        return value
    if method == TransformationMethod.SIGNED_LOG1P:
        return math.copysign(math.log1p(abs(value)), value)
    if lower is None or upper is None:
        raise ValueError("CLIP transformation requires lower and upper bounds")
    return max(lower, min(upper, value))


def normalize_value(
    value: float,
    values: tuple[float, ...],
    method: NormalizationMethod,
    absolute_lower: float | None,
    absolute_upper: float | None,
    robust_scale: float,
) -> float:
    if method == NormalizationMethod.IDENTITY_BOUNDED:
        return max(0.0, min(1.0, value))
    if method == NormalizationMethod.ABSOLUTE_RANGE:
        return _absolute_range(value, absolute_lower, absolute_upper)
    if method == NormalizationMethod.PERCENTILE:
        return average_percentile_rank(value, values)
    center, spread = robust_location_scale(values)
    if spread <= 0.0:
        return 0.5
    return sigmoid((value - center) / (spread * robust_scale))


def _absolute_range(value: float, lower: float | None, upper: float | None) -> float:
    if lower is None or upper is None or upper <= lower:
        raise ValueError("ABSOLUTE_RANGE requires upper > lower")
    return max(0.0, min(1.0, (value - lower) / (upper - lower)))
