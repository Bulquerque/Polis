from __future__ import annotations

import math
from typing import Any

from ._p2_semantic_helpers import artifact, no_forbidden_rows, records, require_inputs
from ._s4_option_helpers import (
    bounded_log_score,
    mean_known,
    optional_number,
    quote_age_seconds,
    source_quality_status,
)


def _index_market(rows: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    by_underlying: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        underlying = row.get("underlying")
        date = row.get("date")
        if underlying not in (None, ""):
            by_underlying.setdefault(str(underlying), []).append(row)
            if date not in (None, ""):
                by_key[(str(underlying), str(date))] = row
    return by_key, by_underlying


def _market_context(quote: dict[str, Any], by_key: dict, by_underlying: dict) -> dict[str, Any] | None:
    underlying = quote.get("underlying")
    date = quote.get("date")
    if underlying not in (None, "") and date not in (None, ""):
        found = by_key.get((str(underlying), str(date)))
        if found:
            return found
    matches = by_underlying.get(str(underlying), []) if underlying not in (None, "") else []
    return matches[0] if len(matches) == 1 else None


def _spread_metrics(quote: dict[str, Any]) -> tuple[float | None, float | None, float | None, float | None]:
    bid = optional_number(quote.get("bid"), field="bid", nonnegative=True)
    ask = optional_number(quote.get("ask"), field="ask", nonnegative=True)
    if bid is None or ask is None or ask < bid:
        return None, None, None, None
    spread = ask - bid
    mid = (ask + bid) / 2.0
    relative = spread / mid if mid > 0 else None
    return spread, spread / 2.0, mid, relative


def _liquidity_score(quote: dict[str, Any], relative_spread: float | None, market: dict[str, Any] | None, config: dict) -> tuple[float | None, list[str]]:
    components: list[float | None] = []
    reasons: list[str] = []

    if relative_spread is not None:
        components.append(1.0 / (1.0 + max(relative_spread, 0.0) * 100.0))
    else:
        reasons.append("SPREAD_UNKNOWN")

    volume = optional_number(quote.get("volume"), field="volume", nonnegative=True)
    oi = optional_number(quote.get("open_interest"), field="open_interest", nonnegative=True)
    components.append(bounded_log_score(volume))
    components.append(bounded_log_score(oi))
    if volume is None:
        reasons.append("VOLUME_UNKNOWN")
    if oi is None:
        reasons.append("OPEN_INTEREST_UNKNOWN")

    age = quote.get("quote_age_seconds")
    if age is None:
        age = quote_age_seconds(quote.get("available_at"), quote.get("as_of_date"))
    if age is not None:
        horizon = float(config.get("liquidity_freshness_horizon_seconds", 86400.0))
        components.append(max(0.0, 1.0 - min(float(age), horizon) / horizon))
    else:
        reasons.append("QUOTE_AGE_UNKNOWN")

    underlying_liquidity = None
    if market:
        underlying_liquidity = market.get("liquidity_score")
        if underlying_liquidity is not None:
            try:
                value = float(underlying_liquidity)
            except (TypeError, ValueError):
                value = None
            if value is not None:
                components.append(max(0.0, min(1.0, value)) if 0 <= value <= 1 else bounded_log_score(value))
        if market.get("tradability_flag") is False:
            reasons.append("UNDERLYING_NON_TRADABLE")
    else:
        reasons.append("UNDERLYING_CONTEXT_UNKNOWN")

    score = mean_known(components)
    return (round(score, 10) if score is not None else None), reasons


def _optional_records(value: Any, artifact_name: str) -> list[dict[str, Any]]:
    if value in ({}, None):
        return []
    return records(value, artifact_name)


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["clean_option_quotes_panel", "clean_underlying_panel", "clean_underlying_trade_panel", "source_quality_panel"]
    require_inputs(inputs, required)

    quotes = records(inputs[required[0]], required[0])
    underlying_rows = _optional_records(inputs[required[1]], required[1])
    trade_rows = _optional_records(inputs[required[2]], required[2])
    _, underlying_by_underlying = _index_market(underlying_rows)
    trade_by_key, trade_by_underlying = _index_market(trade_rows)

    cost_rows: list[dict[str, Any]] = []
    liquidity_rows: list[dict[str, Any]] = []

    for quote in quotes:
        spread, half_spread, mid, relative_spread = _spread_metrics(quote)
        market = _market_context(quote, trade_by_key, trade_by_underlying)
        source_status, source_reasons = source_quality_status(quote, inputs["source_quality_panel"])
        cost_reasons = list(source_reasons)
        if spread is None:
            cost_reasons.append("TWO_SIDED_QUOTE_UNAVAILABLE")
        if market and market.get("tradability_flag") is False:
            cost_reasons.append("UNDERLYING_NON_TRADABLE")

        if spread is None:
            cost_reliability = "UNAVAILABLE"
        elif source_status == "WARN" or cost_reasons:
            cost_reliability = "DEGRADED"
        else:
            cost_reliability = "AVAILABLE"

        common = {
            "date": quote.get("date"),
            "contract_key": quote.get("contract_key") or quote.get("source_id"),
            "underlying": quote.get("underlying"),
            "source_id": quote.get("source_id") or "UNKNOWN",
            "lineage_id": quote.get("lineage_id") or "UNKNOWN",
            "pipeline_version": config.get("pipeline_version", "V14.1-RC4.1"),
        }
        cost_rows.append(
            {
                **common,
                "bid": quote.get("bid"),
                "ask": quote.get("ask"),
                "mid": mid,
                "absolute_spread": spread,
                "half_spread": half_spread,
                "relative_spread": relative_spread,
                "cost_estimate": spread,
                "cost_method": "QUOTED_FULL_SPREAD_REFERENCE_V1",
                "cost_reliability": cost_reliability,
                "quality_reasons": sorted(set(cost_reasons)),
            }
        )

        score, liquidity_reasons = _liquidity_score(quote, relative_spread, market, config)
        liquidity_reasons.extend(source_reasons)
        if score is None:
            liquidity_reliability = "UNAVAILABLE"
        elif liquidity_reasons or source_status == "WARN":
            liquidity_reliability = "DEGRADED"
        else:
            liquidity_reliability = "AVAILABLE"
        liquidity_rows.append(
            {
                **common,
                "volume": quote.get("volume"),
                "open_interest": quote.get("open_interest"),
                "relative_spread": relative_spread,
                "quote_age_seconds": quote.get("quote_age_seconds"),
                "underlying_liquidity_score": (market or {}).get("liquidity_score"),
                "underlying_tradability": (market or {}).get("tradability_flag"),
                "liquidity_score": score,
                "liquidity_score_version": "P2_S4_LIQUIDITY_V1",
                "liquidity_reliability": liquidity_reliability,
                "quality_reasons": sorted(set(liquidity_reasons)),
            }
        )

    no_forbidden_rows(cost_rows)
    no_forbidden_rows(liquidity_rows)
    return {
        "module_id": "P2.S4.M03",
        "module_name": "cost_liquidity_reference_builder",
        "phase": "phase_02_quality_pit",
        "subphase": "P2.S4",
        "contract": "P2_S4_M03_cost_liquidity_reference_builder.yaml",
        "required_inputs": required,
        "outputs": {
            "clean_cost_reference_panel": artifact(
                "clean-cost-reference-panel",
                cost_rows,
                config,
                cost_reference_present=True,
                no_trade_decision=True,
                cost_method="QUOTED_FULL_SPREAD_REFERENCE_V1",
            ),
            "clean_liquidity_reference_panel": artifact(
                "clean-liquidity-reference-panel",
                liquidity_rows,
                config,
                liquidity_reference_present=True,
                no_trade_decision=True,
                liquidity_score_version="P2_S4_LIQUIDITY_V1",
            ),
        },
    }
