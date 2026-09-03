"""Canonical point-in-time reference-price semantics used across P6."""
from __future__ import annotations

from decimal import Decimal

from .market_models import UnderlyingObservation


def reference_spot(observation: UnderlyingObservation) -> Decimal:
    """Use the executable midpoint when bilateral quotes exist, then last/ask/bid.

    A single helper prevents different P6 subphases from valuing the same
    underlying against different anchors.
    """
    if observation.bid is not None and observation.ask is not None:
        return (observation.bid + observation.ask) / Decimal("2")
    for value in (observation.last, observation.ask, observation.bid):
        if value is not None:
            return value
    raise ValueError(f"underlying {observation.underlying_id} has no observable price")
