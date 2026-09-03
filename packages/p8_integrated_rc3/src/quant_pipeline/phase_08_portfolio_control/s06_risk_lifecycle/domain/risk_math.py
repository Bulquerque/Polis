from __future__ import annotations

from collections.abc import Iterable


def weighted_cvar(losses: Iterable[float], probabilities: Iterable[float], alpha: float) -> float:
    pairs = sorted(zip(losses, probabilities, strict=True), key=lambda x: x[0])
    if not pairs:
        raise ValueError("CVaR requires at least one loss")
    total = sum(p for _, p in pairs)
    if abs(total - 1.0) > 1e-9:
        raise ValueError("probabilities must sum to one")
    cumulative = 0.0
    var = pairs[-1][0]
    for loss, probability in pairs:
        cumulative += probability
        if cumulative + 1e-15 >= alpha:
            var = loss
            break
    tail_mass = 1.0 - alpha
    above = [(loss, p) for loss, p in pairs if loss > var]
    above_mass = sum(p for _, p in above)
    var_mass = max(0.0, tail_mass - above_mass)
    tail_sum = sum(loss * p for loss, p in above) + var * var_mass
    return max(0.0, tail_sum / tail_mass)


def maximum_loss(values: Iterable[float]) -> float:
    return max((max(0.0, x) for x in values), default=0.0)
