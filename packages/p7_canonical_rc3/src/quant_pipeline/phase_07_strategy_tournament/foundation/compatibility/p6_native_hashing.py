"""Canonical hashing compatible with the native P6 RC6.1 envelopes."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256
import json
import math
from collections.abc import Mapping


def canonical_value(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return canonical_value(value.value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float is forbidden")
        return value
    if isinstance(value, Mapping):
        return {str(key): canonical_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [canonical_value(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))
    return value


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        canonical_value(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


P6_DECIMAL_FIELDS = frozenset({
    "entry_price_reference", "multiplier", "quantity", "strike", "strategy_scale",
    "entry_cash_flow", "maximum_gain", "maximum_loss", "right_tail_slope",
    "terminal_pnl", "spot_grid", "scenario_cost", "scenario_pnl",
    "scenario_probability", "terminal_payoff", "liquidity_stress", "margin_stress",
    "maximum_path_loss", "expected_net_payoff", "expected_shortfall", "lower_quantile",
    "median_net_payoff", "nominal_utility", "probability_of_profit", "regret",
    "return_on_margin", "return_on_max_loss", "upper_quantile", "value_at_risk",
    "worst_ambiguity_utility", "conservative_entry_cost", "fee_estimate",
    "legging_risk_proxy", "maximum_relative_spread", "quoted_cost", "slippage_estimate",
    "stress_entry_cost", "weakest_leg_liquidity", "delta", "gamma", "vega", "theta",
    "rho", "vanna", "volga", "charm", "margin_confidence", "margin_estimate",
    "relative_scale",
})


def p6_wire_sha256(records: object) -> str:
    """Reconstruct Decimal fields serialized by Pydantic before checking P6 hashes."""
    return canonical_sha256(_restore_decimals(records))


def _restore_decimals(value: object, field_name: str | None = None) -> object:
    if isinstance(value, Mapping):
        return {str(key): _restore_decimals(item, str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [_restore_decimals(item, field_name) for item in value]
    if isinstance(value, tuple):
        return tuple(_restore_decimals(item, field_name) for item in value)
    if isinstance(value, str) and field_name in P6_DECIMAL_FIELDS:
        try:
            return Decimal(value)
        except InvalidOperation:
            return value
    return value
