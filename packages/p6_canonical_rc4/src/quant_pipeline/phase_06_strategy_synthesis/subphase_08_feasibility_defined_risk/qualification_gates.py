"""Structural, maximum-loss, margin, liquidity, cost, and data-quality gates."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from ..domain.enums import CalculationStatus, MarginMethod
from ..domain.models import (
    CandidateQualification,
    CostLiquidityRecord,
    GreekState,
    StrategyCandidate,
    StrategyPayoffRecord,
)
from ..foundation.configuration import Phase6RunConfiguration

ZERO = Decimal("0")

def initial_structural_gate(
    candidates: tuple[StrategyCandidate, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[CandidateQualification, ...]:
    records: list[CandidateQualification] = []
    for candidate in candidates:
        reasons = _structural_reasons(candidate, configuration)
        records.append(
            CandidateQualification(
                candidate_id=candidate.candidate_id,
                qualified=not reasons,
                reason_codes=tuple(reasons),
                maximum_loss_proven=False,
                margin_method=MarginMethod.UNAVAILABLE,
                margin_estimate=None,
                margin_confidence=Decimal("0"),
                margin_status=CalculationStatus.UNAVAILABLE,
                data_quality_status=(
                    CalculationStatus.AVAILABLE
                    if not reasons
                    else CalculationStatus.BLOCKED
                ),
            )
        )
    return tuple(records)

def _structural_reasons(
    candidate: StrategyCandidate,
    configuration: Phase6RunConfiguration,
) -> list[str]:
    reasons: list[str] = []
    if len(candidate.legs) > configuration.budgets.max_legs:
        reasons.append("P6_COMPLEXITY_BUDGET_EXCEEDED")
    if len({leg.leg_id for leg in candidate.legs}) != len(candidate.legs):
        reasons.append("P6_REDUNDANT_LEG")
    if len({leg.currency for leg in candidate.legs}) != 1:
        reasons.append("P6_MIXED_CURRENCY_UNSUPPORTED")
    if len({leg.exchange for leg in candidate.legs}) != 1:
        reasons.append("P6_MIXED_EXCHANGE_UNSUPPORTED")

    expirations = {
        leg.expiration
        for leg in candidate.legs
        if leg.expiration is not None
    }
    if len(expirations) > configuration.budgets.max_expirations:
        reasons.append("P6_COMPLEXITY_BUDGET_EXCEEDED")

    signed_quantities: dict[str, Decimal] = defaultdict(Decimal)
    for leg in candidate.legs:
        direction = Decimal("1") if leg.side.value == "LONG" else Decimal("-1")
        signed_quantities[leg.instrument_id] += direction * leg.quantity
    if any(value == ZERO for value in signed_quantities.values()):
        reasons.append("P6_REDUNDANT_LEG")
    return sorted(set(reasons))


def apply_maximum_loss_gate(
    qualifications: tuple[CandidateQualification, ...],
    payoffs: tuple[StrategyPayoffRecord, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[CandidateQualification, ...]:
    payoff_by_id = {item.candidate_id: item for item in payoffs}
    output: list[CandidateQualification] = []
    for item in qualifications:
        payoff = payoff_by_id[item.candidate_id]
        reasons = list(item.reason_codes)
        proven = (
            payoff.maximum_loss is not None
            and payoff.right_tail_slope >= ZERO
        )
        if configuration.risk.require_defined_risk and not proven:
            reasons.append("P6_MAXIMUM_LOSS_NOT_PROVEN")
        output.append(
            item.model_copy(
                update={
                    "qualified": not reasons,
                    "reason_codes": tuple(sorted(set(reasons))),
                    "maximum_loss_proven": proven,
                }
            )
        )
    return tuple(output)


def apply_margin_gate(
    qualifications: tuple[CandidateQualification, ...],
    payoffs: tuple[StrategyPayoffRecord, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[CandidateQualification, ...]:
    payoff_by_id = {item.candidate_id: item for item in payoffs}
    output: list[CandidateQualification] = []
    for item in qualifications:
        payoff = payoff_by_id[item.candidate_id]
        reasons = list(item.reason_codes)
        margin = payoff.maximum_loss if item.maximum_loss_proven else None
        method = (
            MarginMethod.DEFINED_RISK_UPPER_BOUND
            if margin is not None
            else MarginMethod.UNAVAILABLE
        )
        if configuration.risk.require_margin_estimate and margin is None:
            reasons.append("P6_MARGIN_UNAVAILABLE")
        if _margin_exceeds_limit(margin, configuration):
            reasons.append("P6_MARGIN_LIMIT_EXCEEDED")
        output.append(
            item.model_copy(
                update={
                    "qualified": not reasons,
                    "reason_codes": tuple(sorted(set(reasons))),
                    "margin_method": method,
                    "margin_estimate": margin,
                    "margin_confidence": (
                        Decimal("0.9") if margin is not None else Decimal("0")
                    ),
                    "margin_status": (
                        CalculationStatus.AVAILABLE
                        if margin is not None
                        else CalculationStatus.UNAVAILABLE
                    ),
                }
            )
        )
    return tuple(output)


def _margin_exceeds_limit(
    margin: Decimal | None,
    configuration: Phase6RunConfiguration,
) -> bool:
    limit = configuration.risk.maximum_loss_limit
    return limit is not None and margin is not None and margin > limit


def apply_liquidity_gate(
    qualifications: tuple[CandidateQualification, ...],
    costs: tuple[CostLiquidityRecord, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[CandidateQualification, ...]:
    cost_by_id = {item.candidate_id: item for item in costs}
    output: list[CandidateQualification] = []
    for item in qualifications:
        cost = cost_by_id[item.candidate_id]
        reasons = list(item.reason_codes)
        if cost.status is CalculationStatus.UNAVAILABLE or cost.status is CalculationStatus.BLOCKED:
            reasons.append("P6_LIQUIDITY_UNAVAILABLE")
        elif cost.status is CalculationStatus.DEGRADED and not configuration.risk.allow_degraded_liquidity:
            reasons.append("P6_LIQUIDITY_DEGRADED")
        if configuration.risk.require_complete_liquidity_metrics and (
            cost.weakest_leg_liquidity is None
            or cost.maximum_relative_spread is None
        ):
            reasons.append("P6_LIQUIDITY_METRICS_INCOMPLETE")
        if _liquidity_below_minimum(cost, configuration):
            reasons.append("P6_LIQUIDITY_BELOW_MINIMUM")
        if _spread_above_maximum(cost, configuration):
            reasons.append("P6_RELATIVE_SPREAD_ABOVE_MAXIMUM")
        output.append(_with_reasons(item, reasons))
    return tuple(output)


def _liquidity_below_minimum(
    cost: CostLiquidityRecord,
    configuration: Phase6RunConfiguration,
) -> bool:
    value = cost.weakest_leg_liquidity
    return (
        value is not None
        and value < configuration.risk.minimum_liquidity_score
    )


def _spread_above_maximum(
    cost: CostLiquidityRecord,
    configuration: Phase6RunConfiguration,
) -> bool:
    value = cost.maximum_relative_spread
    return (
        value is not None
        and value > configuration.risk.maximum_relative_spread
    )


def apply_cost_gate(
    qualifications: tuple[CandidateQualification, ...],
    costs: tuple[CostLiquidityRecord, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[CandidateQualification, ...]:
    cost_by_id = {item.candidate_id: item for item in costs}
    output: list[CandidateQualification] = []
    for item in qualifications:
        cost = cost_by_id[item.candidate_id]
        reasons = list(item.reason_codes)
        limit = configuration.risk.maximum_entry_cost
        if limit is not None and cost.conservative_entry_cost > limit:
            reasons.append("P6_COST_LIMIT_EXCEEDED")
        output.append(_with_reasons(item, reasons))
    return tuple(output)


def apply_data_quality_gate(
    qualifications: tuple[CandidateQualification, ...],
    greeks: tuple[GreekState, ...],
) -> tuple[CandidateQualification, ...]:
    greek_by_id = {item.candidate_id: item for item in greeks}
    output: list[CandidateQualification] = []
    for item in qualifications:
        greek = greek_by_id[item.candidate_id]
        reasons = list(item.reason_codes)
        if greek.status is not CalculationStatus.AVAILABLE:
            reasons.append("P6_OUTPUT_SCHEMA_INVALID")
        status = (
            CalculationStatus.AVAILABLE
            if greek.status is CalculationStatus.AVAILABLE
            else CalculationStatus.BLOCKED
        )
        output.append(
            item.model_copy(
                update={
                    "qualified": not reasons,
                    "reason_codes": tuple(sorted(set(reasons))),
                    "data_quality_status": status,
                }
            )
        )
    return tuple(output)


def _with_reasons(
    item: CandidateQualification,
    reasons: list[str],
) -> CandidateQualification:
    unique = tuple(sorted(set(reasons)))
    return item.model_copy(
        update={
            "qualified": not unique,
            "reason_codes": unique,
        }
    )


