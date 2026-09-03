from __future__ import annotations

from decimal import Decimal

from .enums import AlertSeverity, ReasonCode
from .models_invariants import (
    InvariantMonitorRequest,
    InvariantMonitorResult,
    InvariantViolation,
)


def _violation(
    invariant_id: str,
    severity: AlertSeverity,
    code: ReasonCode,
    expected: object,
    actual: object,
) -> InvariantViolation:
    return InvariantViolation(
        invariant_id=invariant_id,
        severity=severity,
        reason_code=code,
        expected=str(expected),
        actual=str(actual),
    )


def _quantity_checks(request: InvariantMonitorRequest) -> list[InvariantViolation]:
    s, p = request.snapshot, request.policy
    violations: list[InvariantViolation] = []
    if s.received_candidate_count != s.terminal_candidate_count:
        violations.append(_violation(
            "candidate_conservation", AlertSeverity.STATE_INCONSISTENT,
            ReasonCode.CANDIDATE_CONSERVATION_FAIL,
            s.received_candidate_count, s.terminal_candidate_count,
        ))
    resolved = s.filled_quantity + s.cancelled_quantity + s.rejected_quantity + s.open_quantity
    if abs(s.order_total_quantity - resolved) > p.quantity_tolerance:
        violations.append(_violation(
            "order_conservation", AlertSeverity.STATE_INCONSISTENT,
            ReasonCode.ORDER_CONSERVATION_FAIL, s.order_total_quantity, resolved,
        ))
    if abs(s.virtual_exposure_total - s.physical_allocated_total) > p.exposure_tolerance:
        violations.append(_violation(
            "dual_book_reconciliation", AlertSeverity.STATE_INCONSISTENT,
            ReasonCode.DUAL_BOOK_RECONCILIATION_FAIL,
            s.virtual_exposure_total, s.physical_allocated_total,
        ))
    return violations


def _account_checks(request: InvariantMonitorRequest) -> list[InvariantViolation]:
    s, p = request.snapshot, request.policy
    violations: list[InvariantViolation] = []
    expected_cash = s.opening_cash + s.net_cash_flows
    if abs(expected_cash - s.closing_cash) > p.money_tolerance:
        violations.append(_violation(
            "cash_reconciliation", AlertSeverity.STATE_INCONSISTENT,
            ReasonCode.CASH_RECONCILIATION_FAIL, expected_cash, s.closing_cash,
        ))
    headroom = (s.margin_limit - s.margin_used) / s.margin_limit
    if headroom < p.minimum_margin_headroom_ratio:
        severity = AlertSeverity.CRITICAL if headroom < Decimal("0") else AlertSeverity.MATERIAL
        violations.append(_violation(
            "margin_headroom", severity, ReasonCode.MARGIN_HEADROOM_BREACH,
            p.minimum_margin_headroom_ratio, headroom,
        ))
    if s.maximum_loss > s.maximum_loss_limit:
        violations.append(_violation(
            "maximum_loss", AlertSeverity.CRITICAL, ReasonCode.MAX_LOSS_BREACH,
            s.maximum_loss_limit, s.maximum_loss,
        ))
    return violations


def _state_checks(request: InvariantMonitorRequest) -> list[InvariantViolation]:
    s = request.snapshot
    violations: list[InvariantViolation] = []
    if s.quote_age_seconds > s.maximum_quote_age_seconds:
        violations.append(_violation(
            "quote_freshness", AlertSeverity.MATERIAL, ReasonCode.QUOTE_STALE,
            s.maximum_quote_age_seconds, s.quote_age_seconds,
        ))
    if not s.lifecycle_consistent:
        violations.append(_violation(
            "lifecycle", AlertSeverity.CRITICAL, ReasonCode.LIFECYCLE_INCONSISTENT,
            True, False,
        ))
    if not s.settlement_consistent:
        violations.append(_violation(
            "settlement", AlertSeverity.CRITICAL, ReasonCode.SETTLEMENT_INCONSISTENT,
            True, False,
        ))
    if s.expected_state_hash != s.actual_state_hash:
        violations.append(_violation(
            "state_hash", AlertSeverity.STATE_INCONSISTENT, ReasonCode.STATE_HASH_MISMATCH,
            s.expected_state_hash, s.actual_state_hash,
        ))
    return violations


def _highest(violations: list[InvariantViolation]) -> AlertSeverity:
    order = {
        AlertSeverity.INFO: 0,
        AlertSeverity.CAUTION: 1,
        AlertSeverity.MATERIAL: 2,
        AlertSeverity.CRITICAL: 3,
        AlertSeverity.STATE_INCONSISTENT: 4,
        AlertSeverity.MONITOR_FAILURE: 5,
    }
    return max((v.severity for v in violations), key=order.get, default=AlertSeverity.INFO)


def run_invariant_monitor(request: InvariantMonitorRequest) -> InvariantMonitorResult:
    violations = _quantity_checks(request) + _account_checks(request) + _state_checks(request)
    ordered = tuple(sorted(violations, key=lambda item: item.invariant_id))
    return InvariantMonitorResult(
        healthy=not ordered,
        highest_severity=_highest(list(ordered)),
        violations=ordered,
    )
