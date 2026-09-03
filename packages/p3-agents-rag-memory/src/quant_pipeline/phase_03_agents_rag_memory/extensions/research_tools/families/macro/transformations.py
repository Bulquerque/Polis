from __future__ import annotations

import math
from collections.abc import Sequence

from .result_contracts import MacroObservation
from .types import Frequency, Transformation

_PERIODS_PER_YEAR = {
    Frequency.DAILY: 252,
    Frequency.WEEKLY: 52,
    Frequency.MONTHLY: 12,
    Frequency.QUARTERLY: 4,
    Frequency.ANNUAL: 1,
}


def required_lag(
    frequency: Frequency,
    transformation: Transformation,
) -> int:
    if transformation is Transformation.LEVEL:
        return 0
    if transformation is Transformation.YEAR_OVER_YEAR:
        lag = _PERIODS_PER_YEAR.get(frequency)
        if lag is None:
            raise ValueError("YEAR_OVER_YEAR requires a known regular frequency")
        return lag
    return 1


def apply_transformation(
    observations: Sequence[MacroObservation],
    transformation: Transformation,
) -> tuple[MacroObservation, ...]:
    ordered = tuple(sorted(observations, key=lambda item: item.observation_date))
    if transformation is Transformation.LEVEL:
        return tuple(
            item.model_copy(
                update={"transformation": transformation, "value": item.raw_value}
            )
            for item in ordered
        )
    if not ordered:
        return ()
    lag = required_lag(ordered[0].frequency, transformation)
    result: list[MacroObservation] = []
    for index in range(lag, len(ordered)):
        current = ordered[index]
        previous = ordered[index - lag]
        value = _transform_value(current.raw_value, previous.raw_value, transformation, current.frequency)
        result.append(current.model_copy(update={"value": value, "transformation": transformation}))
    return tuple(result)


def _transform_value(
    current: float,
    previous: float,
    transformation: Transformation,
    frequency: Frequency,
) -> float:
    if transformation is Transformation.DIFFERENCE:
        return current - previous
    if transformation in {Transformation.PERCENT_CHANGE, Transformation.YEAR_OVER_YEAR}:
        if previous == 0:
            raise ValueError("percentage transformation cannot divide by zero")
        return ((current / previous) - 1.0) * 100.0
    if transformation is Transformation.LOG_DIFFERENCE:
        if current <= 0 or previous <= 0:
            raise ValueError("LOG_DIFFERENCE requires positive values")
        return (math.log(current) - math.log(previous)) * 100.0
    if transformation is Transformation.ANNUALIZED:
        periods = _PERIODS_PER_YEAR.get(frequency)
        if periods is None:
            raise ValueError("ANNUALIZED requires a known regular frequency")
        if previous == 0:
            raise ValueError("annualized transformation cannot divide by zero")
        gross = current / previous
        if gross <= 0:
            raise ValueError("annualized transformation requires positive gross growth")
        return ((gross**periods) - 1.0) * 100.0
    raise ValueError(f"unsupported transformation: {transformation}")
