"""Risk-neutral state diagnostics derived from one coherent call surface."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from ..domain.enums import CalculationStatus, OptionType
from ..domain.models import (
    ExecutableQuote,
    MarketBeliefState,
    MarketImpliedState,
    OptionContractReference,
)
from ..foundation.configuration import (
    P5CompatibilityPolicy,
    Phase6RunConfiguration,
    PricingPolicy,
)
from ..foundation.hashing import stable_id
from ..subphase_01_boundary_market_snapshot.services import quote_mid

ZERO = Decimal("0")
CallPoint = tuple[OptionContractReference, Decimal]
SurfaceKey = tuple[str, datetime, str, Decimal, str]


def estimate_market_implied_states(
    beliefs: tuple[MarketBeliefState, ...],
    contracts: tuple[OptionContractReference, ...],
    quotes: tuple[ExecutableQuote, ...],
    decision_time: datetime,
    configuration: Phase6RunConfiguration | None = None,
) -> tuple[MarketImpliedState, ...]:
    """Estimate one maturity-consistent discrete risk-neutral state per belief."""
    surfaces = _call_surfaces(contracts, quotes)
    p5_policy = configuration.p5 if configuration is not None else P5CompatibilityPolicy()
    pricing_policy = configuration.pricing if configuration is not None else PricingPolicy()
    return tuple(
        _implied_state(
            belief,
            _surface_for_belief(belief, surfaces, decision_time, p5_policy),
            decision_time,
            pricing_policy,
        )
        for belief in beliefs
    )


def _call_surfaces(
    contracts: tuple[OptionContractReference, ...],
    quotes: tuple[ExecutableQuote, ...],
) -> dict[SurfaceKey, tuple[CallPoint, ...]]:
    quote_by_id = {item.contract_id: item for item in quotes}
    grouped: dict[SurfaceKey, list[CallPoint]] = defaultdict(list)
    for contract in contracts:
        if contract.option_type is not OptionType.CALL:
            continue
        quote = quote_by_id.get(contract.contract_id)
        price = None if quote is None else quote_mid(quote)
        if price is None:
            continue
        key = (
            contract.underlying_id,
            contract.expiration,
            contract.currency,
            contract.multiplier,
            contract.exercise_style.value,
        )
        grouped[key].append((contract, price))
    return {
        key: tuple(sorted(values, key=lambda item: item[0].strike))
        for key, values in grouped.items()
    }


def _call_points(
    contracts: tuple[OptionContractReference, ...],
    quotes: tuple[ExecutableQuote, ...],
) -> dict[str, tuple[CallPoint, ...]]:
    """Legacy inspection helper; canonical estimation uses maturity surfaces."""
    surfaces = _call_surfaces(contracts, quotes)
    grouped: dict[str, list[CallPoint]] = defaultdict(list)
    for key, points in surfaces.items():
        grouped[key[0]].extend(points)
    return {
        underlying: tuple(sorted(points, key=lambda item: (item[0].expiration, item[0].strike)))
        for underlying, points in grouped.items()
    }


def _surface_for_belief(
    belief: MarketBeliefState,
    surfaces: dict[SurfaceKey, tuple[CallPoint, ...]],
    decision_time: datetime,
    p5_policy: P5CompatibilityPolicy,
) -> tuple[SurfaceKey | None, tuple[CallPoint, ...]]:
    candidates = [
        (key, points)
        for key, points in surfaces.items()
        if key[0] == belief.underlying_id
    ]
    if not candidates:
        return None, ()
    target = _target_time(
        decision_time,
        belief.horizon_days,
        p5_policy.horizon_time_basis,
    )
    future = [item for item in candidates if item[0][1] >= target]
    pool = future or candidates
    key, points = min(
        pool,
        key=lambda item: (
            abs((item[0][1] - target).total_seconds()),
            -len(item[1]),
            item[0][1],
            item[0][2],
            str(item[0][3]),
            item[0][4],
        ),
    )
    gap = abs((key[1].date() - target.date()).days)
    if gap > p5_policy.maximum_expiration_gap_days:
        return None, ()
    return key, points


def _implied_state(
    belief: MarketBeliefState,
    surface: tuple[SurfaceKey | None, tuple[CallPoint, ...]] | tuple[CallPoint, ...],
    decision_time: datetime,
    pricing_policy: PricingPolicy | None = None,
) -> MarketImpliedState:
    pricing_policy = pricing_policy or PricingPolicy()
    key, points = _coerce_surface(surface)
    if len(points) < 3:
        return _unavailable_state(
            belief,
            key,
            points,
            decision_time,
            "P6_MARKET_IMPLIED_DENSITY_INSUFFICIENT_STRIKES",
            pricing_policy,
        )
    grid, masses = _curvature_masses(points)
    total = sum(masses, ZERO)
    if total <= ZERO:
        return _blocked_state(belief, points, decision_time, pricing_policy, key=key)
    probabilities = tuple(value / total for value in masses)
    coverage = Decimal(len(grid)) / Decimal(max(len(points), 1))
    if key is None:
        key = _surface_key_from_points(points)
    return MarketImpliedState(
        market_implied_state_id=stable_id(
            "market-implied",
            belief.underlying_id,
            key,
            grid,
            probabilities,
        ),
        underlying_id=belief.underlying_id,
        decision_time=decision_time,
        state_grid=grid,
        risk_neutral_probabilities=probabilities,
        method="MATURITY_CONSISTENT_CALL_CONVEXITY",
        smoothing="NONNEGATIVE_SECOND_DIFFERENCE",
        repair_status=CalculationStatus.AVAILABLE,
        strike_coverage=coverage,
        tail_extrapolation_status=CalculationStatus.UNAVAILABLE,
        source_contract_ids=_contract_ids(points),
        source_expiration=None if key is None else key[1],
        source_currency=None if key is None else key[2],
        source_multiplier=None if key is None else key[3],
        source_exercise_style=None if key is None else key[4],
        risk_free_rate=pricing_policy.risk_free_rate,
        dividend_yield=pricing_policy.dividend_yield,
        status=CalculationStatus.AVAILABLE,
    )


def _coerce_surface(
    surface: tuple[SurfaceKey | None, tuple[CallPoint, ...]] | tuple[CallPoint, ...],
) -> tuple[SurfaceKey | None, tuple[CallPoint, ...]]:
    if len(surface) == 2 and (
        surface[0] is None
        or isinstance(surface[0], tuple) and len(surface[0]) == 5 and isinstance(surface[1], tuple)
    ):
        key, points = surface
        return key, points
    points = surface
    return _surface_key_from_points(points), points


def _surface_key_from_points(points: tuple[CallPoint, ...]) -> SurfaceKey | None:
    if not points:
        return None
    contract = points[0][0]
    return (
        contract.underlying_id,
        contract.expiration,
        contract.currency,
        contract.multiplier,
        contract.exercise_style.value,
    )


def _curvature_masses(
    points: tuple[CallPoint, ...],
) -> tuple[tuple[Decimal, ...], tuple[Decimal, ...]]:
    grid: list[Decimal] = []
    masses: list[Decimal] = []
    for left, middle, right in zip(points, points[1:], points[2:]):
        left_width = middle[0].strike - left[0].strike
        right_width = right[0].strike - middle[0].strike
        if left_width <= ZERO or right_width <= ZERO:
            continue
        left_slope = (middle[1] - left[1]) / left_width
        right_slope = (right[1] - middle[1]) / right_width
        grid.append(middle[0].strike)
        masses.append(max(right_slope - left_slope, ZERO))
    return tuple(grid), tuple(masses)


def _unavailable_state(
    belief: MarketBeliefState,
    key: SurfaceKey | None,
    points: tuple[CallPoint, ...],
    decision_time: datetime,
    reason_code: str,
    pricing_policy: PricingPolicy,
) -> MarketImpliedState:
    return MarketImpliedState(
        market_implied_state_id=stable_id(
            "market-implied", belief.underlying_id, "unavailable", key
        ),
        underlying_id=belief.underlying_id,
        decision_time=decision_time,
        state_grid=(),
        risk_neutral_probabilities=(),
        method="MATURITY_CONSISTENT_CALL_CONVEXITY",
        smoothing="NONE",
        repair_status=CalculationStatus.UNAVAILABLE,
        strike_coverage=ZERO,
        tail_extrapolation_status=CalculationStatus.UNAVAILABLE,
        source_contract_ids=_contract_ids(points),
        source_expiration=None if key is None else key[1],
        source_currency=None if key is None else key[2],
        source_multiplier=None if key is None else key[3],
        source_exercise_style=None if key is None else key[4],
        risk_free_rate=pricing_policy.risk_free_rate,
        dividend_yield=pricing_policy.dividend_yield,
        status=CalculationStatus.UNAVAILABLE,
        reason_code=reason_code,
    )


def _blocked_state(
    belief: MarketBeliefState,
    points: tuple[CallPoint, ...],
    decision_time: datetime,
    pricing_policy: PricingPolicy | None = None,
    *,
    key: SurfaceKey | None = None,
) -> MarketImpliedState:
    pricing_policy = pricing_policy or PricingPolicy()
    key = key or _surface_key_from_points(points)
    record = _unavailable_state(
        belief,
        key,
        points,
        decision_time,
        "P6_STATIC_ARBITRAGE_VIOLATION",
        pricing_policy,
    )
    return record.model_copy(
        update={
            "market_implied_state_id": stable_id(
                "market-implied", belief.underlying_id, "nonpositive", key
            ),
            "repair_status": CalculationStatus.BLOCKED,
            "status": CalculationStatus.BLOCKED,
        }
    )


def _target_time(decision_time: datetime, horizon_days: int, basis: str) -> datetime:
    if basis == "CALENDAR_DAYS":
        return decision_time + timedelta(days=horizon_days)
    if basis == "TRADING_DAYS_WEEKDAY":
        cursor = decision_time
        remaining = horizon_days
        while remaining:
            cursor += timedelta(days=1)
            if cursor.weekday() < 5:
                remaining -= 1
        return cursor
    raise ValueError(f"unsupported horizon_time_basis: {basis}")


def _contract_ids(points: tuple[CallPoint, ...]) -> tuple[str, ...]:
    return tuple(item.contract_id for item, _ in points)
