"""Deterministic contract selection aligned with P5 belief horizons."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from ..domain.enums import CapabilityStatus, OptionType
from ..domain.market_price import reference_spot
from ..domain.models import (
    ExecutableQuote,
    MarketBeliefState,
    OptionContractReference,
    UnderlyingObservation,
)
from ..foundation.configuration import Phase6RunConfiguration


class TemplatePlan:
    def __init__(
        self,
        contracts: tuple[OptionContractReference, ...],
        quotes: tuple[ExecutableQuote, ...],
        underlyings: tuple[UnderlyingObservation, ...],
        beliefs: tuple[MarketBeliefState, ...],
        configuration: Phase6RunConfiguration,
    ) -> None:
        self.quote_by_id = {item.contract_id: item for item in quotes}
        self.underlying_by_id = {item.underlying_id: item for item in underlyings}
        self.belief_by_underlying = _select_beliefs(beliefs, configuration)
        self.active_underlying_ids = tuple(
            sorted(set(self.underlying_by_id).intersection(self.belief_by_underlying))
        )
        grouped: dict[tuple[str, str, OptionType], list[OptionContractReference]] = defaultdict(list)
        for item in contracts:
            grouped[(item.underlying_id, item.expiration.isoformat(), item.option_type)].append(item)
        self.groups = {
            key: tuple(sorted(values, key=lambda item: item.strike))
            for key, values in grouped.items()
        }
        self.configuration = configuration

    def horizon_days(self, underlying_id: str) -> int:
        return self.belief_by_underlying[underlying_id].horizon_days

    def first_expiration(self, underlying_id: str) -> str | None:
        expirations = sorted({key[1] for key in self.groups if key[0] == underlying_id})
        if not expirations:
            return None
        target = _target_time(
            self.configuration.decision_time,
            self.horizon_days(underlying_id),
            self.configuration.p5.horizon_time_basis,
        )
        parsed = [(value, _parse_expiration(value)) for value in expirations]
        policy = self.configuration.p5.option_expiration_selection
        if self.configuration.p5.require_exact_option_horizon_match:
            policy = "EXACT"
        selected = _select_expiration(parsed, target, policy)
        if selected is None:
            return None
        gap = abs((selected[1].date() - target.date()).days)
        if gap > self.configuration.p5.maximum_expiration_gap_days:
            return None
        return selected[0]

    def contracts(self, underlying_id: str, option_type: OptionType) -> tuple[OptionContractReference, ...]:
        expiration = self.first_expiration(underlying_id)
        if expiration is None:
            return ()
        contracts = self.groups.get((underlying_id, expiration, option_type), ())
        spot = self.spot(underlying_id)
        ordered = sorted(contracts, key=lambda item: (abs(item.strike - spot), item.strike))
        limited = ordered[: self.configuration.budgets.max_contracts_considered]
        return tuple(sorted(limited, key=lambda item: item.strike))

    def spot(self, underlying_id: str) -> Decimal:
        return reference_spot(self.underlying_by_id[underlying_id])


def _select_beliefs(
    beliefs: tuple[MarketBeliefState, ...],
    configuration: Phase6RunConfiguration,
) -> dict[str, MarketBeliefState]:
    grouped: dict[str, list[MarketBeliefState]] = defaultdict(list)
    for belief in beliefs:
        if belief.scenario_capability is not CapabilityStatus.AVAILABLE or not belief.scenarios:
            continue
        if belief.abstained is True and not configuration.p5.allow_abstained_beliefs:
            continue
        grouped[belief.underlying_id].append(belief)
    selected: dict[str, MarketBeliefState] = {}
    preferred = configuration.p5.preferred_horizon_days
    for underlying_id, candidates in grouped.items():
        if preferred is not None:
            matching = [item for item in candidates if item.horizon_days == preferred]
            if matching:
                candidates = matching
        selected[underlying_id] = sorted(
            candidates,
            key=lambda item: (-item.confidence, item.horizon_days, item.belief_state_id),
        )[0]
    return selected


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


def _select_expiration(
    parsed: list[tuple[str, datetime]],
    target: datetime,
    policy: str,
) -> tuple[str, datetime] | None:
    if policy == "EXACT":
        exact = [item for item in parsed if item[1].date() == target.date()]
        return exact[0] if exact else None
    if policy == "FIRST_ON_OR_AFTER":
        future = [item for item in parsed if item[1].date() >= target.date()]
        if future:
            return min(future, key=lambda item: (item[1], item[0]))
        return None
    if policy == "NEAREST":
        return min(parsed, key=lambda item: (abs((item[1] - target).total_seconds()), item[0]))
    raise ValueError(f"unsupported option_expiration_selection: {policy}")


def _parse_expiration(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
