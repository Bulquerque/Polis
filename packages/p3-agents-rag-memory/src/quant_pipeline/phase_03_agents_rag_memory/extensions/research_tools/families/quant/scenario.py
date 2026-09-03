"""Explicit linear and quadratic scenario shocks without probability or optimization."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from .request_models import QuadraticExposure


def scenario_value(
    *,
    baseline_value: float,
    factor_shocks: Mapping[str, float],
    linear_exposures: Mapping[str, float],
    quadratic_exposures: Sequence[QuadraticExposure],
    multiplier: float = 1.0,
) -> tuple[float, dict[str, float]]:
    contributions: dict[str, float] = {}
    total_change = 0.0
    for factor in sorted(factor_shocks):
        shock = factor_shocks[factor] * multiplier
        contribution = linear_exposures.get(factor, 0.0) * shock
        contributions[f"linear:{factor}"] = contribution
        total_change += contribution
    for term in quadratic_exposures:
        contribution = (
            term.coefficient
            * factor_shocks[term.left_factor]
            * factor_shocks[term.right_factor]
            * multiplier
            * multiplier
        )
        key = f"quadratic:{term.left_factor}:{term.right_factor}"
        contributions[key] = contribution
        total_change += contribution
    return baseline_value + total_change, contributions
