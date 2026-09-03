"""P8.S4.M04 liquidity capacity and execution-risk state builder."""
from __future__ import annotations

from datetime import timezone

import numpy as np

from ..contracts import (
    CandidateEconomicPackage,
    CandidateLiquidityState,
    ComponentQuality,
    LiquidityPolicy,
    LiquidityQuote,
    LiquiditySummary,
    MarketLiquiditySnapshot,
)
from ..hashing import canonical_sha256
from ..ports import ExecutionRiskEstimatorPort

MODULE_ID = "P8.S4.M04"


def _spread_bps(bid: float, ask: float) -> float:
    midpoint = 0.5 * (bid + ask)
    return 0.0 if midpoint <= 0.0 else 10_000.0 * (ask - bid) / midpoint


def _instrument_capacity(quote: LiquidityQuote, policy: LiquidityPolicy) -> float | None:
    limits = [min(quote.bid_size, quote.ask_size) * policy.depth_multiplier]
    if quote.daily_volume is not None:
        limits.append(quote.daily_volume * policy.volume_participation)
    if quote.open_interest is not None:
        limits.append(quote.open_interest * policy.open_interest_participation)
    finite = [value for value in limits if np.isfinite(value)]
    return max(min(finite), 0.0) if finite else None


def _rule_based_execution_risk(
    spread_bps: float,
    capacity_units: float,
    leg_count: int,
    combo_available: bool,
    policy: LiquidityPolicy,
) -> tuple[float, float, float]:
    spread_score = float(np.clip(1.0 - spread_bps / policy.max_spread_bps, 0.0, 1.0))
    capacity_score = float(capacity_units / (capacity_units + 1.0))
    fill = spread_score * capacity_score
    if combo_available and leg_count > 1:
        fill = min(1.0, fill + policy.combo_fill_bonus)
    partial = float(np.clip(1.0 - fill**max(leg_count, 1), 0.0, 1.0))
    return fill, partial, 0.0 if combo_available or leg_count <= 1 else partial


def _leg_liquidity(
    leg,
    quote_map: dict[str, LiquidityQuote],
    decision_time,
    policy: LiquidityPolicy,
) -> tuple[tuple[str, float, float, str | None] | None, str | None]:
    quote = quote_map.get(leg.instrument_id)
    if quote is None:
        return None, f"DEPTH_UNAVAILABLE:{leg.leg_id}"
    age = (
        decision_time.astimezone(timezone.utc) - quote.quote_time.astimezone(timezone.utc)
    ).total_seconds()
    if age > policy.max_quote_age_seconds:
        return None, f"QUOTE_STALE:{leg.leg_id}"
    capacity = _instrument_capacity(quote, policy)
    if capacity is None:
        return None, f"LIQUIDITY_CAPACITY_UNAVAILABLE:{leg.leg_id}"
    requirement = abs(leg.quantity_per_unit)
    if requirement <= 0.0:
        return None, f"INVALID_UNIT_REQUIREMENT:{leg.leg_id}"
    return (
        leg.leg_id,
        capacity / requirement,
        _spread_bps(quote.bid, quote.ask),
        quote.combo_group_id,
    ), None


def _execution_estimate(
    candidate_id: str,
    capacity_units: float,
    max_spread: float,
    leg_count: int,
    combo_available: bool,
    policy: LiquidityPolicy,
    estimator: ExecutionRiskEstimatorPort | None,
) -> tuple[float, float, float, ComponentQuality, tuple[str, ...]]:
    if estimator is None:
        fill, partial, legging = _rule_based_execution_risk(
            max_spread, capacity_units, leg_count, combo_available, policy,
        )
        return fill, partial, legging, ComponentQuality.DEGRADED, ("EXECUTION_RISK_RULE_BASED",)
    estimate = estimator.estimate(candidate_id, capacity_units)
    quality = (
        ComponentQuality.FULLY_QUALIFIED
        if estimate.quality_status == "QUALIFIED"
        else ComponentQuality.DEGRADED
    )
    return (
        estimate.fill_probability,
        estimate.partial_fill_risk,
        estimate.legging_risk,
        quality,
        estimate.reason_codes,
    )


def _candidate_liquidity_state(
    candidate: CandidateEconomicPackage,
    quote_map: dict[str, LiquidityQuote],
    snapshot: MarketLiquiditySnapshot,
    haircut: float,
    policy: LiquidityPolicy,
    estimator: ExecutionRiskEstimatorPort | None,
) -> CandidateLiquidityState:
    results = [
        _leg_liquidity(leg, quote_map, snapshot.decision_time, policy)
        for leg in candidate.legs
    ]
    reasons = [reason for _, reason in results if reason is not None]
    legs = [result for result, _ in results if result is not None]
    if len(legs) != len(candidate.legs):
        return CandidateLiquidityState(
            candidate_id=candidate.candidate_id,
            fidelity=ComponentQuality.UNAVAILABLE,
            reason_codes=tuple(reasons or ("LIQUIDITY_CAPACITY_UNAVAILABLE",)),
        )
    weakest_leg_id, raw_capacity, _, _ = min(legs, key=lambda item: item[1])
    capacity_units = max(raw_capacity * (1.0 - haircut), 0.0)
    max_spread = max(item[2] for item in legs)
    groups = [item[3] for item in legs]
    combo = len(legs) > 1 and groups[0] is not None and all(group == groups[0] for group in groups)
    fill, partial, legging, quality, extra = _execution_estimate(
        candidate.candidate_id, capacity_units, max_spread, len(legs), combo, policy, estimator,
    )
    reasons.extend(extra)
    if fill < policy.min_fill_probability:
        quality = ComponentQuality.UNAVAILABLE
        reasons.append("FILL_PROBABILITY_BELOW_FLOOR")
    return CandidateLiquidityState(
        candidate_id=candidate.candidate_id,
        capacity_units=capacity_units,
        weakest_leg_id=weakest_leg_id,
        spread_bps=max_spread,
        fill_probability_one_unit=fill,
        partial_fill_risk=partial,
        legging_risk=legging,
        fidelity=quality,
        reason_codes=tuple(reasons),
    )


def build_liquidity_state(
    candidates: tuple[CandidateEconomicPackage, ...],
    snapshot: MarketLiquiditySnapshot,
    liquidity_haircut: float,
    policy: LiquidityPolicy,
    estimator: ExecutionRiskEstimatorPort | None = None,
) -> LiquiditySummary:
    quote_map = {quote.instrument_id: quote for quote in snapshot.quotes}
    states = tuple(
        _candidate_liquidity_state(
            candidate, quote_map, snapshot, liquidity_haircut, policy, estimator,
        ) for candidate in candidates
    )
    return LiquiditySummary(
        states=states,
        content_sha256=canonical_sha256({"states": states}),
    )
