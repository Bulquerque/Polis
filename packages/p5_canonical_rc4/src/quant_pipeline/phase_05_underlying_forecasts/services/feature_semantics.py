"""Exact semantic feature aliases for the P4 V14.9 feature vocabulary.

No fuzzy or substring matching is permitted.  Every alias is reviewed and
versioned so a feature cannot silently change economic meaning.
"""
from __future__ import annotations

from typing import Iterable

SEMANTIC_REGISTRY_VERSION = "P4-V14.9-P5-RC34.1-CONTRACT-CLOSURE-RC4-SEMANTICS-V2"

_ALIASES: dict[str, tuple[str, ...]] = {
    "return_state": (
        "perspective.momentum.time_series",
        "perspective.reversion.short_term",
    ),
    "realized_risk_state": (
        "perspective.risk.multiscale",
        "perspective.risk.downside",
    ),
    "drawdown_state": ("perspective.risk.drawdown_stress",),
    "liquidity_state": (
        "perspective.liquidity.price_impact",
        "perspective.liquidity.participation",
    ),
    "implied_volatility_state": (
        "options.atm_implied_volatility",
        "perspective.risk.multiscale",
    ),
    "regime_state": (
        "perspective.macro.growth_state",
        "perspective.macro.inflation_state",
        "perspective.structure.common_mode_proxy",
        "perspective.structure.contagion_pressure_proxy",
        "perspective.carry.curve_slope_state",
    ),
}


def aliases(role: str) -> tuple[str, ...]:
    try:
        return _ALIASES[role]
    except KeyError as exc:
        raise KeyError(f"unknown feature semantic role: {role}") from exc


def first_available(role: str, available: Iterable[str]) -> str | None:
    available_set = set(available)
    return next((name for name in aliases(role) if name in available_set), None)
