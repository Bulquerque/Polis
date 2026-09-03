"""P9.S3.M04 — backtest integrity and deterministic replay gate."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .common import content_sha256
from .integrity_models import (
    BacktestQualificationReceipt,
    CandidateTerminalState,
    CashCategory,
    CheckResult,
    P8EvaluationHandoff,
    QualificationState,
    ReconciliationTolerance,
    Side,
)
from .reason_codes import ReasonCode


def replay_handoff_sha256(handoff: P8EvaluationHandoff) -> str:
    """Hash the immutable replay preimage, excluding the asserted replay hash."""

    return content_sha256(handoff.model_dump(mode="python", exclude={"replay_sha256"}))



def finalize_handoff_replay_hash(handoff: P8EvaluationHandoff) -> P8EvaluationHandoff:
    """Return a validated copy containing the canonical replay hash."""

    payload = handoff.model_dump(mode="python")
    payload["replay_sha256"] = replay_handoff_sha256(handoff)
    return P8EvaluationHandoff.model_validate(payload)


def _close(left: Decimal, right: Decimal, tolerance: Decimal) -> bool:
    return abs(left - right) <= tolerance


def qualify_backtest(
    handoff: P8EvaluationHandoff,
    tolerance: ReconciliationTolerance | None = None,
) -> BacktestQualificationReceipt:
    """Run independent conservation, accounting, lifecycle, and replay checks."""

    tolerance = tolerance or ReconciliationTolerance()
    checks: list[CheckResult] = []
    reasons: set[str] = set()

    def add(
        check_id: str,
        passed: bool,
        observed: object,
        expected: object,
        reason: ReasonCode,
    ) -> None:
        checks.append(
            CheckResult(
                check_id=check_id,
                passed=passed,
                observed=str(observed),
                expected=str(expected),
                reason_code=None if passed else reason.value,
            )
        )
        if not passed:
            reasons.add(reason.value)

    if handoff.capability == "LEGACY_RESEARCH_ONLY":
        reasons.add(ReasonCode.LEGACY_P8_NOT_QUALIFIABLE.value)

    p6 = set(handoff.p6_candidate_ids)
    p7_ids = [item.candidate_id for item in handoff.p7_terminal_records]
    p8_ids = [item.candidate_id for item in handoff.p8_terminal_records]
    add(
        "candidate_conservation_p6_to_p7",
        p6 == set(p7_ids) and len(p7_ids) == len(p6),
        sorted(p7_ids),
        sorted(p6),
        ReasonCode.CANDIDATE_CONSERVATION_FAILED,
    )
    add(
        "candidate_conservation_p8_subset",
        set(p8_ids).issubset(p6),
        sorted(p8_ids),
        f"subset of {sorted(p6)}",
        ReasonCode.CANDIDATE_CONSERVATION_FAILED,
    )

    p7_state = {item.candidate_id: item.state for item in handoff.p7_terminal_records}
    executed_candidates = {
        order.candidate_id
        for order in handoff.orders
        if order.candidate_id is not None
    }
    blocked_states = {
        CandidateTerminalState.BLOCKED,
        CandidateTerminalState.ABSTAINED,
    }
    prohibited = {
        candidate_id
        for candidate_id in executed_candidates
        if p7_state.get(candidate_id) in blocked_states
    }
    add(
        "blocked_or_abstained_not_executed",
        not prohibited,
        sorted(prohibited),
        "empty",
        ReasonCode.CANDIDATE_CONSERVATION_FAILED,
    )

    orders = {order.order_id: order for order in handoff.orders}
    fill_quantities: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    fill_cash_expected: dict[str, Decimal] = {}
    order_fill_valid = True
    for fill in handoff.fills:
        order = orders.get(fill.order_id)
        if order is None or order.instrument_id != fill.instrument_id or order.side != fill.side:
            order_fill_valid = False
            continue
        fill_quantities[fill.order_id] += fill.quantity
        sign = Decimal("-1") if fill.side is Side.BUY else Decimal("1")
        fill_cash_expected[fill.fill_id] = sign * fill.quantity * fill.price - fill.fee
    for order_id, quantity in fill_quantities.items():
        if quantity - orders[order_id].quantity > tolerance.quantity:
            order_fill_valid = False
    add(
        "order_fill_reconciliation",
        order_fill_valid,
        dict(fill_quantities),
        "fills reference matching orders and do not exceed quantity",
        ReasonCode.ORDER_FILL_MISMATCH,
    )

    fill_cash_actual: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for entry in handoff.cash_entries:
        if entry.category is CashCategory.FILL and entry.related_fill_id is not None:
            fill_cash_actual[entry.related_fill_id] += entry.amount
    fill_cash_ok = set(fill_cash_actual) == set(fill_cash_expected)
    if fill_cash_ok:
        fill_cash_ok = all(
            _close(fill_cash_actual[fill_id], expected, tolerance.money)
            for fill_id, expected in fill_cash_expected.items()
        )
    add(
        "fill_cash_reconciliation",
        fill_cash_ok,
        dict(fill_cash_actual),
        dict(fill_cash_expected),
        ReasonCode.ACCOUNTING_MISMATCH,
    )

    cash_expected = handoff.start_cash + sum(
        (entry.amount for entry in handoff.cash_entries),
        Decimal("0"),
    )
    add(
        "cash_ledger_identity",
        _close(cash_expected, handoff.end_cash, tolerance.money),
        handoff.end_cash,
        cash_expected,
        ReasonCode.ACCOUNTING_MISMATCH,
    )

    expected_positions: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for fill in handoff.fills:
        position_delta = fill.quantity if fill.side is Side.BUY else -fill.quantity
        expected_positions[fill.instrument_id] += position_delta
    for event in handoff.lifecycle_events:
        expected_positions[event.instrument_id] += event.quantity_delta
    actual_positions = {item.instrument_id: item.quantity for item in handoff.final_positions}
    all_instruments = set(expected_positions) | set(actual_positions)
    positions_ok = all(
        _close(
            expected_positions[instrument],
            actual_positions.get(instrument, Decimal("0")),
            tolerance.quantity,
        )
        for instrument in all_instruments
    )
    add(
        "position_reconciliation",
        positions_ok,
        actual_positions,
        dict(expected_positions),
        ReasonCode.POSITION_RECONCILIATION_FAILED,
    )

    valuation_ok = True
    for record in handoff.valuations:
        valuation_ok &= _close(record.nav, record.cash + record.market_value, tolerance.money)
        valuation_ok &= _close(record.net_pnl, record.gross_pnl - record.costs, tolerance.money)
    valuation_ok &= _close(handoff.valuations[-1].cash, handoff.end_cash, tolerance.money)
    add(
        "valuation_identities",
        valuation_ok,
        handoff.valuations[-1],
        "nav=cash+market_value and net_pnl=gross_pnl-costs",
        ReasonCode.ACCOUNTING_MISMATCH,
    )

    add(
        "required_lifecycle_supported",
        handoff.required_lifecycle_supported,
        handoff.required_lifecycle_supported,
        True,
        ReasonCode.LIFECYCLE_UNSUPPORTED,
    )

    computed_replay = replay_handoff_sha256(handoff)
    add(
        "replay_hash",
        computed_replay == handoff.replay_sha256,
        handoff.replay_sha256,
        computed_replay,
        ReasonCode.REPLAY_DIVERGED,
    )

    no_action = not handoff.orders and not handoff.fills
    if handoff.capability == "LEGACY_RESEARCH_ONLY":
        state = QualificationState.LEGACY_RESEARCH_ONLY
    elif reasons:
        state = QualificationState.INVALID
        reasons.add(ReasonCode.BACKTEST_INVALID.value)
    elif no_action:
        state = QualificationState.NO_ACTION_VALID
    else:
        state = QualificationState.QUALIFIED

    qualified_hash = handoff.replay_sha256 if state in {
        QualificationState.QUALIFIED,
        QualificationState.NO_ACTION_VALID,
    } else None
    body = {
        "handoff_id": handoff.handoff_id,
        "state": state,
        "checks": tuple(checks),
        "reason_codes": tuple(sorted(reasons)),
        "qualified_handoff_sha256": qualified_hash,
    }
    return BacktestQualificationReceipt(
        **body,
        content_sha256=content_sha256(body),
    )
