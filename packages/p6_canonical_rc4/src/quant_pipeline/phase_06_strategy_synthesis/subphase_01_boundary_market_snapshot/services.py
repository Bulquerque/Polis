"""Boundary validation, static-arbitrage diagnostics, and immutable PIT snapshot."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from ..domain.enums import OptionType, QuoteQuality
from ..domain.models import (
    ExecutableQuote,
    MarketBeliefState,
    OptionContractReference,
    StaticArbitrageViolation,
    StrategyMarketSnapshot,
    UnderlyingObservation,
)
from ..foundation.hashing import canonical_sha256, stable_id

ZERO = Decimal("0")


def quote_mid(quote: ExecutableQuote) -> Decimal | None:
    if quote.bid is not None and quote.ask is not None:
        return (quote.bid + quote.ask) / Decimal("2")
    return quote.last


def _observed_price(observation: UnderlyingObservation) -> Decimal | None:
    for value in (observation.last, observation.ask, observation.bid):
        if value is not None:
            return value
    return None


def classify_quote(quote: ExecutableQuote) -> ExecutableQuote:
    quality = quote.quote_quality
    if quote.bid is not None and quote.ask is not None:
        quality = QuoteQuality.CROSSED if quote.bid > quote.ask else QuoteQuality.TWO_SIDED_EXECUTABLE
    elif quote.bid is not None:
        quality = QuoteQuality.ONE_SIDED_BID
    elif quote.ask is not None:
        quality = QuoteQuality.ONE_SIDED_ASK
    elif quote.last is not None:
        quality = QuoteQuality.TRADE_ONLY
    else:
        quality = QuoteQuality.UNAVAILABLE
    return quote.model_copy(update={"quote_quality": quality})


def static_arbitrage_diagnostics(
    contracts: tuple[OptionContractReference, ...],
    quotes: tuple[ExecutableQuote, ...],
    underlyings: tuple[UnderlyingObservation, ...],
) -> tuple[StaticArbitrageViolation, ...]:
    contract_by_id = {item.contract_id: item for item in contracts}
    underlying_by_id = {item.underlying_id: item for item in underlyings}
    violations: list[StaticArbitrageViolation] = []
    prices_by_slice: dict[tuple[str, str, str], list[tuple[Decimal, Decimal, str]]] = defaultdict(list)
    for quote in quotes:
        contract = contract_by_id.get(quote.contract_id)
        if contract is None:
            violations.append(_violation("UNKNOWN_CONTRACT", (quote.contract_id,), "BLOCKING", {}))
            continue
        if quote.bid is not None and quote.ask is not None and quote.bid > quote.ask:
            violations.append(_violation("BID_ABOVE_ASK", (quote.contract_id,), "BLOCKING", {}))
        price = quote_mid(quote)
        observation = underlying_by_id.get(contract.underlying_id)
        spot = None if observation is None else _observed_price(observation)
        if price is not None and spot is not None:
            intrinsic = (
                max(spot - contract.strike, ZERO)
                if contract.option_type is OptionType.CALL
                else max(contract.strike - spot, ZERO)
            )
            if price < intrinsic:
                violations.append(_violation(
                    "INTRINSIC_BOUND",
                    (quote.contract_id,),
                    "BLOCKING",
                    {"price": str(price), "intrinsic": str(intrinsic)},
                ))
            key = (contract.underlying_id, contract.expiration.isoformat(), contract.option_type.value)
            prices_by_slice[key].append((contract.strike, price, contract.contract_id))
    for key, points in prices_by_slice.items():
        ordered = sorted(points)
        for left, right in zip(ordered, ordered[1:]):
            if key[2] == OptionType.CALL.value and right[1] > left[1]:
                violations.append(_violation("VERTICAL_MONOTONICITY", (left[2], right[2]), "BLOCKING", {}))
            if key[2] == OptionType.PUT.value and right[1] < left[1]:
                violations.append(_violation("VERTICAL_MONOTONICITY", (left[2], right[2]), "BLOCKING", {}))
        for first, middle, last in zip(ordered, ordered[1:], ordered[2:]):
            left_width = middle[0] - first[0]
            right_width = last[0] - middle[0]
            if left_width > ZERO and right_width > ZERO:
                left_slope = (middle[1] - first[1]) / left_width
                right_slope = (last[1] - middle[1]) / right_width
                if right_slope < left_slope:
                    violations.append(_violation(
                        "BUTTERFLY_CONVEXITY",
                        (first[2], middle[2], last[2]),
                        "BLOCKING",
                        {},
                    ))
    return tuple(violations)


def _violation(
    violation_type: str,
    contract_ids: tuple[str, ...],
    severity: str,
    details: dict[str, str],
) -> StaticArbitrageViolation:
    return StaticArbitrageViolation(
        violation_id=stable_id("arbitrage", violation_type, contract_ids, details),
        violation_type=violation_type,
        severity=severity,
        contract_ids=contract_ids,
        details=details,
    )


def build_snapshot(
    *,
    decision_time,
    belief_artifact_id: str,
    contract_artifact_id: str,
    quote_artifact_id: str,
    underlying_artifact_id: str,
    rejection_report_artifact_id: str,
    p5_compatibility_report_artifact_id: str | None = None,
    p5_manifest_id: str | None = None,
    p5_manifest_sha256: str | None = None,
    p5_source_artifact_ids: tuple[str, ...] = (),
    p5_source_hashes: tuple[str, ...] = (),
    beliefs: tuple[MarketBeliefState, ...],
    contracts: tuple[OptionContractReference, ...],
    quotes: tuple[ExecutableQuote, ...],
    underlyings: tuple[UnderlyingObservation, ...],
) -> StrategyMarketSnapshot:
    snapshot_hash = canonical_sha256({
        "beliefs": beliefs,
        "contracts": contracts,
        "quotes": quotes,
        "underlyings": underlyings,
        "p5_manifest_id": p5_manifest_id,
        "p5_manifest_sha256": p5_manifest_sha256,
        "p5_source_artifact_ids": p5_source_artifact_ids,
        "p5_source_hashes": p5_source_hashes,
    })
    return StrategyMarketSnapshot(
        snapshot_id=stable_id("market-snapshot", decision_time, snapshot_hash),
        decision_time=decision_time,
        belief_artifact_id=belief_artifact_id,
        contract_artifact_id=contract_artifact_id,
        quote_artifact_id=quote_artifact_id,
        underlying_artifact_id=underlying_artifact_id,
        rejection_report_artifact_id=rejection_report_artifact_id,
        p5_compatibility_report_artifact_id=p5_compatibility_report_artifact_id,
        p5_manifest_id=p5_manifest_id,
        p5_manifest_sha256=p5_manifest_sha256,
        p5_source_artifact_ids=p5_source_artifact_ids,
        p5_source_hashes=p5_source_hashes,
        snapshot_sha256=snapshot_hash,
        contract_count=len(contracts),
        quote_count=len(quotes),
        underlying_count=len(underlyings),
    )
