"""Canonical candidate identities independent of generation order."""

from __future__ import annotations

from decimal import Decimal
from math import gcd
from functools import reduce

from ..foundation.hashing import stable_id
from .models import StrategyCandidate, StrategyLeg


def signed_quantity(leg: StrategyLeg) -> Decimal:
    return leg.quantity if leg.side.value == "LONG" else -leg.quantity


def leg_sort_key(leg: StrategyLeg) -> tuple[str, ...]:
    return (
        leg.instrument_type.value,
        leg.instrument_id,
        leg.option_type.value if leg.option_type else "",
        "" if leg.strike is None else str(leg.strike),
        leg.expiration.isoformat() if leg.expiration else "",
        leg.side.value,
        str(leg.quantity),
    )


def canonical_leg_payload(legs: tuple[StrategyLeg, ...]) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "instrument_id": leg.instrument_id,
            "instrument_type": leg.instrument_type.value,
            "side": leg.side.value,
            "quantity": str(leg.quantity),
            "option_type": leg.option_type.value if leg.option_type else "",
            "strike": "" if leg.strike is None else str(leg.strike),
            "expiration": leg.expiration.isoformat() if leg.expiration else "",
            "multiplier": str(leg.multiplier),
        }
        for leg in sorted(legs, key=leg_sort_key)
    )


def candidate_id(
    *,
    underlying_id: str,
    decision_time: str,
    legs: tuple[StrategyLeg, ...],
    objective_family: str,
    policy_version: str,
    horizon_days: int,
) -> str:
    return stable_id(
        "candidate",
        underlying_id,
        decision_time,
        canonical_leg_payload(legs),
        objective_family,
        horizon_days,
        policy_version,
    )


def integer_scale(legs: tuple[StrategyLeg, ...]) -> int:
    integers: list[int] = []
    for leg in legs:
        value = signed_quantity(leg)
        if value != value.to_integral_value():
            return 1
        integers.append(abs(int(value)))
    nonzero = [value for value in integers if value]
    return reduce(gcd, nonzero) if nonzero else 1


def shape_fingerprint(candidate: StrategyCandidate) -> tuple[str, Decimal]:
    scale = integer_scale(candidate.legs)
    normalized = []
    for leg in sorted(candidate.legs, key=leg_sort_key):
        normalized.append({
            "instrument_id": leg.instrument_id,
            "instrument_type": leg.instrument_type.value,
            "signed_quantity": str(signed_quantity(leg) / Decimal(scale)),
            "strike": "" if leg.strike is None else str(leg.strike),
            "expiration": leg.expiration.isoformat() if leg.expiration else "",
        })
    return stable_id("shape", normalized), Decimal(scale)
