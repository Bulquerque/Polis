"""Canonical leg and template-candidate builders for P6.S3."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal

from ..domain.enums import (
    InstrumentType,
    LegRole,
    ObjectiveFamily,
    OriginMode,
    Side,
    TemplateId,
)
from ..domain.identity import candidate_id
from ..domain.models import (
    CandidateGenerationTrace,
    ExecutableQuote,
    OptionContractReference,
    StrategyCandidate,
    StrategyLeg,
)
from ..foundation.configuration import Phase6RunConfiguration
from ..foundation.hashing import stable_id
from .planning import TemplatePlan

CandidatePair = tuple[StrategyCandidate, CandidateGenerationTrace]
CandidateAppender = Callable[[TemplateId, ObjectiveFamily, Sequence[StrategyLeg]], None]


def option_leg(
    contract: OptionContractReference,
    quote: ExecutableQuote,
    side: Side,
    quantity: int,
    role: LegRole,
) -> StrategyLeg:
    """Build one executable option leg using the appropriate book side."""
    price = quote.ask if side is Side.LONG else quote.bid
    if price is None:
        raise ValueError("executable side is unavailable")
    return StrategyLeg(
        leg_id=stable_id("leg", contract.contract_id, side, quantity, role),
        instrument_id=contract.contract_id,
        instrument_type=InstrumentType.OPTION,
        side=side,
        quantity=Decimal(quantity),
        option_type=contract.option_type,
        strike=contract.strike,
        expiration=contract.expiration,
        exercise_style=contract.exercise_style,
        settlement_type=contract.settlement_type,
        multiplier=contract.multiplier,
        currency=contract.currency,
        exchange=contract.listing_exchange,
        entry_price_reference=price,
        price_selection_method="ASK" if side is Side.LONG else "BID",
        leg_role=role,
        quote_quality=quote.quote_quality,
        source_quote_id=quote.source_id,
    )


def underlying_leg(
    plan: TemplatePlan,
    underlying_id: str,
    side: Side,
    role: LegRole,
) -> StrategyLeg:
    """Build one executable underlying leg using the appropriate book side."""
    observation = plan.underlying_by_id[underlying_id]
    price = observation.ask if side is Side.LONG else observation.bid
    if price is None:
        raise ValueError("underlying executable side is unavailable")
    return StrategyLeg(
        leg_id=stable_id("leg", underlying_id, side, role),
        instrument_id=underlying_id,
        instrument_type=InstrumentType.UNDERLYING,
        side=side,
        quantity=Decimal("1"),
        multiplier=Decimal("1"),
        currency=observation.currency,
        exchange=observation.exchange,
        entry_price_reference=price,
        price_selection_method="ASK" if side is Side.LONG else "BID",
        leg_role=role,
    )


def make_candidate(
    template: TemplateId,
    objective: ObjectiveFamily,
    underlying_id: str,
    legs: tuple[StrategyLeg, ...],
    configuration: Phase6RunConfiguration,
    *,
    horizon_days: int,
) -> CandidatePair:
    """Build a deterministic candidate and its immutable generation trace."""
    identifier = candidate_id(
        underlying_id=underlying_id,
        decision_time=configuration.decision_time.isoformat(),
        legs=legs,
        objective_family=objective.value,
        policy_version=configuration.strategy.policy_version,
        horizon_days=horizon_days,
    )
    candidate = StrategyCandidate(
        candidate_id=identifier,
        candidate_version="1",
        underlying_id=underlying_id,
        decision_time=configuration.decision_time,
        horizon_days=horizon_days,
        objective_family=objective,
        origin_mode=OriginMode.TEMPLATE,
        origin_template_id=template,
        legs=legs,
        strategy_scale=Decimal("1"),
        generation_run_id=configuration.run_id,
        lineage_id=stable_id("candidate-lineage", identifier, configuration.run_id),
    )
    trace = CandidateGenerationTrace(
        candidate_id=identifier,
        origin=OriginMode.TEMPLATE,
        origin_template_id=template,
        generation_stage="P6.S3",
        parameters={"policy_version": configuration.strategy.policy_version},
    )
    return candidate, trace
