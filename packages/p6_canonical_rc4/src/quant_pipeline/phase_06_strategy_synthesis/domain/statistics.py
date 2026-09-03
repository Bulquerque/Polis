"""Small deterministic weighted statistics used by scenario qualification."""

from __future__ import annotations

from decimal import Decimal

ZERO = Decimal("0")


def weighted_mean(values: list[Decimal], probabilities: list[Decimal]) -> Decimal:
    return sum((value * probability for value, probability in zip(values, probabilities)), ZERO)


def weighted_quantile(
    values: list[Decimal],
    probabilities: list[Decimal],
    level: Decimal,
) -> Decimal:
    ordered = sorted(zip(values, probabilities), key=lambda item: item[0])
    cumulative = ZERO
    for value, probability in ordered:
        cumulative += probability
        if cumulative >= level:
            return value
    return ordered[-1][0]


def expected_shortfall(
    values: list[Decimal],
    probabilities: list[Decimal],
    alpha: Decimal = Decimal("0.05"),
) -> Decimal:
    threshold = weighted_quantile(values, probabilities, alpha)
    tail = [(v, p) for v, p in zip(values, probabilities) if v <= threshold]
    mass = sum((p for _, p in tail), ZERO)
    if mass == ZERO:
        return ZERO
    return -sum((v * p for v, p in tail), ZERO) / mass
