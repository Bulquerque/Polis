"""Regularization and qualification of target payoff records."""

from __future__ import annotations

from decimal import Decimal
from math import isfinite

from ..domain.enums import CalculationStatus
from ..domain.models import (
    TargetPayoffQualification,
    TargetPayoffRecord,
    TargetPayoffRegularizationReport,
)
from ..foundation.configuration import Phase6RunConfiguration

ZERO = Decimal("0")
ONE = Decimal("1")


def regularize_targets(
    targets: tuple[TargetPayoffRecord, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[
    tuple[TargetPayoffRecord, ...],
    tuple[TargetPayoffRegularizationReport, ...],
]:
    """Clip, smooth, normalize, and confidence-shrink target payoffs."""
    output: list[TargetPayoffRecord] = []
    reports: list[TargetPayoffRegularizationReport] = []
    for target in targets:
        updated, report = _regularize_target(target, configuration)
        output.append(updated)
        reports.append(report)
    return tuple(output), tuple(reports)


def qualify_targets(
    targets: tuple[TargetPayoffRecord, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[TargetPayoffQualification, ...]:
    """Fail closed when a target is unavailable, non-finite, or unbounded."""
    return tuple(
        _qualification(target, configuration)
        for target in targets
    )


def _regularize_target(
    target: TargetPayoffRecord,
    configuration: Phase6RunConfiguration,
) -> tuple[TargetPayoffRecord, TargetPayoffRegularizationReport]:
    raw = target.raw_target_payoff
    policy = configuration.target_payoff
    if target.status is not CalculationStatus.AVAILABLE or not raw:
        report = TargetPayoffRegularizationReport(
            target_payoff_id=target.target_payoff_id,
            raw_range=ZERO,
            regularized_range=ZERO,
            clipping_count=0,
            smoothing_strength=policy.smoothing_strength,
            confidence_shrinkage=policy.confidence_shrinkage,
            finite=False,
        )
        return target, report
    clipped, clipping_count = _clip(raw, policy.clipping_multiple)
    smoothed = _smooth(clipped, policy.smoothing_strength)
    normalized = _normalize(smoothed)
    confidence_factor = ONE - policy.confidence_shrinkage * (
        ONE - target.confidence
    )
    regularized = tuple(
        value * confidence_factor * policy.target_notional
        for value in normalized
    )
    updated = target.model_copy(
        update={"regularized_target_payoff": regularized}
    )
    report = TargetPayoffRegularizationReport(
        target_payoff_id=target.target_payoff_id,
        raw_range=max(raw) - min(raw),
        regularized_range=max(regularized) - min(regularized),
        clipping_count=clipping_count,
        smoothing_strength=policy.smoothing_strength,
        confidence_shrinkage=policy.confidence_shrinkage,
        finite=all(isfinite(float(value)) for value in regularized),
    )
    return updated, report


def _qualification(
    target: TargetPayoffRecord,
    configuration: Phase6RunConfiguration,
) -> TargetPayoffQualification:
    values = target.regularized_target_payoff
    finite = all(isfinite(float(value)) for value in values)
    bound = configuration.target_payoff.target_notional * Decimal("1.0000001")
    bounded = all(abs(value) <= bound for value in values)
    confidence = (
        target.confidence
        >= configuration.target_payoff.minimum_confidence
    )
    reasons = _qualification_reasons(target, finite, bounded, confidence)
    return TargetPayoffQualification(
        target_payoff_id=target.target_payoff_id,
        qualified=not reasons,
        reason_codes=reasons,
        finite=finite,
        bounded=bounded,
        confidence_sufficient=confidence,
        cost_budget_available=target.cost_budget is not None,
        risk_budget_available=target.risk_budget is not None,
    )


def _qualification_reasons(
    target: TargetPayoffRecord,
    finite: bool,
    bounded: bool,
    confidence: bool,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if target.status is not CalculationStatus.AVAILABLE:
        reasons.append(target.reason_code or "P6_TARGET_PAYOFF_UNAVAILABLE")
    if not finite:
        reasons.append("P6_PAYOFF_NON_FINITE")
    if not bounded:
        reasons.append("P6_TARGET_PAYOFF_UNBOUNDED")
    if not confidence:
        reasons.append("P6_TARGET_PAYOFF_CONFIDENCE_BELOW_MINIMUM")
    return tuple(reasons)


def _clip(
    values: tuple[Decimal, ...],
    multiple: Decimal,
) -> tuple[tuple[Decimal, ...], int]:
    magnitude = max((abs(value) for value in values), default=ONE)
    positive = [abs(value) for value in values if value != ZERO]
    reference = sorted(positive)[len(positive) // 2] if positive else magnitude
    limit = max(reference * multiple, ONE)
    clipped = tuple(max(min(value, limit), -limit) for value in values)
    count = sum(left != right for left, right in zip(values, clipped))
    return clipped, count


def _smooth(
    values: tuple[Decimal, ...],
    strength: Decimal,
) -> tuple[Decimal, ...]:
    if len(values) < 3 or strength == ZERO:
        return values
    output = [values[0]]
    for left, center, right in zip(values, values[1:], values[2:]):
        neighborhood = (left + center + right) / Decimal("3")
        output.append(center * (ONE - strength) + neighborhood * strength)
    output.append(values[-1])
    return tuple(output)


def _normalize(values: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    magnitude = max((abs(value) for value in values), default=ZERO)
    if magnitude == ZERO:
        return values
    return tuple(value / magnitude for value in values)
