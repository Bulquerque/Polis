from __future__ import annotations
import hashlib
from collections import defaultdict
from decimal import Decimal
from .enums import AuditCheckStatus, AuditOverallStatus, LedgerCategory, OrderSide, PnLQuality, ReasonCode
from .models_audit import AuditCheck, IndependentAuditReport
from .models_state import StatefulEvidenceBundle
from .replay import replay_hash, validate_event_sequence

def _audit_id(bundle: StatefulEvidenceBundle) -> str:
    raw = f"{bundle.context.run_id}|{bundle.context.cycle_id}|{bundle.bundle_id}"
    return "aud_" + hashlib.sha256(raw.encode()).hexdigest()[:20]

def _status(residual: Decimal, tolerance: Decimal) -> AuditCheckStatus:
    return AuditCheckStatus.PASS if abs(residual) <= tolerance else AuditCheckStatus.FAIL

def _check(check_id: str, residual: Decimal, tolerance: Decimal, reason: ReasonCode,
           expected: object, observed: object) -> AuditCheck:
    status = _status(residual, tolerance)
    reasons = () if status == AuditCheckStatus.PASS else (reason,)
    return AuditCheck(check_id=check_id, status=status, reason_codes=reasons,
                      expected_value=str(expected), observed_value=str(observed), residual=residual)

def _candidate_check(bundle: StatefulEvidenceBundle) -> AuditCheck:
    expected = set(bundle.expected_candidate_ids)
    observed = [row.candidate_id for row in bundle.candidate_states]
    valid = len(observed) == len(set(observed)) and set(observed) == expected
    return AuditCheck(
        check_id="candidate_conservation",
        status=AuditCheckStatus.PASS if valid else AuditCheckStatus.FAIL,
        reason_codes=() if valid else (ReasonCode.CANDIDATE_CONSERVATION_FAIL,),
        expected_value=",".join(sorted(expected)), observed_value=",".join(sorted(observed)),
    )

def _identity_check(check_id: str, values: list[str], reason: ReasonCode) -> AuditCheck:
    valid = len(values) == len(set(values))
    return AuditCheck(check_id=check_id, status=AuditCheckStatus.PASS if valid else AuditCheckStatus.FAIL,
        reason_codes=() if valid else (reason,), observed_value=",".join(values))

def _fill_identity_checks(bundle: StatefulEvidenceBundle) -> list[AuditCheck]:
    orders = {order.order_id: order for order in bundle.orders}
    valid = True
    for fill in bundle.fills:
        order = orders.get(fill.order_id)
        valid &= order is not None and order.instrument_id == fill.instrument_id and order.side == fill.side
    return [
        _identity_check("order_id_uniqueness", [x.order_id for x in bundle.orders], ReasonCode.ORDER_CONSERVATION_FAIL),
        _identity_check("fill_id_uniqueness", [x.fill_id for x in bundle.fills], ReasonCode.FILL_LEDGER_MISMATCH),
        AuditCheck(check_id="fill_order_identity", status=AuditCheckStatus.PASS if valid else AuditCheckStatus.FAIL,
            reason_codes=() if valid else (ReasonCode.FILL_LEDGER_MISMATCH,)),
    ]

def _order_checks(bundle: StatefulEvidenceBundle) -> list[AuditCheck]:
    fill_sums: dict[str, Decimal] = defaultdict(Decimal)
    for fill in bundle.fills:
        fill_sums[fill.order_id] += fill.quantity
    checks: list[AuditCheck] = []
    order_ids = {order.order_id for order in bundle.orders}
    orphan = sorted({fill.order_id for fill in bundle.fills} - order_ids)
    for order in bundle.orders:
        parts = order.filled_quantity + order.cancelled_quantity + order.rejected_quantity + order.open_quantity
        checks.append(_check(f"order_conservation:{order.order_id}", parts-order.total_quantity,
                             bundle.tolerance.absolute, ReasonCode.ORDER_CONSERVATION_FAIL,
                             order.total_quantity, parts))
        checks.append(_check(f"fill_sum:{order.order_id}", fill_sums[order.order_id]-order.filled_quantity,
                             bundle.tolerance.absolute, ReasonCode.FILL_LEDGER_MISMATCH,
                             order.filled_quantity, fill_sums[order.order_id]))
    if orphan:
        checks.append(AuditCheck(check_id="orphan_fills", status=AuditCheckStatus.FAIL,
            reason_codes=(ReasonCode.FILL_LEDGER_MISMATCH,), observed_value=",".join(orphan)))
    return checks

def _signed(side: OrderSide, quantity: Decimal) -> Decimal:
    return quantity if side == OrderSide.BUY else -quantity

def _position_check(bundle: StatefulEvidenceBundle) -> AuditCheck:
    expected: dict[str, Decimal] = defaultdict(Decimal)
    for row in bundle.initial_positions:
        expected[row.instrument_id] += row.quantity
    for fill in bundle.fills:
        expected[fill.instrument_id] += _signed(fill.side, fill.quantity)
    observed: dict[str, Decimal] = defaultdict(Decimal)
    for row in bundle.final_positions:
        observed[row.instrument_id] += row.quantity
    keys = set(expected) | set(observed)
    residual = sum(abs(expected[key]-observed[key]) for key in keys)
    return _check("position_reconciliation", residual, bundle.tolerance.absolute,
                  ReasonCode.POSITION_RECONCILIATION_FAIL,
                  dict(sorted(expected.items())), dict(sorted(observed.items())))

def _dual_book_check(bundle: StatefulEvidenceBundle) -> AuditCheck:
    allocated: dict[str, Decimal] = defaultdict(Decimal)
    candidates = set(bundle.expected_candidate_ids)
    invalid_candidate = False
    for row in bundle.virtual_allocations:
        allocated[row.instrument_id] += row.quantity
        invalid_candidate |= row.candidate_id not in candidates
    physical: dict[str, Decimal] = defaultdict(Decimal)
    for row in bundle.final_positions:
        physical[row.instrument_id] += row.quantity
    keys = set(allocated) | set(physical)
    residual = sum(abs(allocated[key]-physical[key]) for key in keys)
    if invalid_candidate:
        residual += bundle.tolerance.absolute + Decimal("1")
    return _check("dual_book_reconciliation", residual, bundle.tolerance.absolute,
                  ReasonCode.DUAL_BOOK_RECONCILIATION_FAIL,
                  dict(sorted(physical.items())), dict(sorted(allocated.items())))

def _ledger_sums(bundle: StatefulEvidenceBundle) -> dict[LedgerCategory, Decimal]:
    sums: dict[LedgerCategory, Decimal] = defaultdict(Decimal)
    for entry in bundle.ledger_entries:
        sums[entry.category] += entry.amount
    return sums

def _account_checks(bundle: StatefulEvidenceBundle) -> list[AuditCheck]:
    account = bundle.account_snapshot
    if not account.currency_accounts:
        sums = _ledger_sums(bundle)
        final_cash = account.initial_cash + sums[LedgerCategory.CASH_FLOW] + sums[LedgerCategory.PREMIUM] + sums[LedgerCategory.COST]
        return [
            _check("cash_reconciliation", final_cash-account.final_cash, bundle.tolerance.absolute,
                   ReasonCode.CASH_RECONCILIATION_FAIL, account.final_cash, final_cash),
            _check("margin_reconciliation", sums[LedgerCategory.MARGIN]-account.margin_used,
                   bundle.tolerance.absolute, ReasonCode.MARGIN_RECONCILIATION_FAIL,
                   account.margin_used, sums[LedgerCategory.MARGIN]),
            _check("collateral_reconciliation", sums[LedgerCategory.COLLATERAL]-account.collateral_value,
                   bundle.tolerance.absolute, ReasonCode.COLLATERAL_RECONCILIATION_FAIL,
                   account.collateral_value, sums[LedgerCategory.COLLATERAL]),
            _check("liability_reconciliation", sums[LedgerCategory.LIABILITY]-account.liabilities,
                   bundle.tolerance.absolute, ReasonCode.CASH_RECONCILIATION_FAIL,
                   account.liabilities, sums[LedgerCategory.LIABILITY]),
        ]

    sums_by_currency: dict[str, dict[LedgerCategory, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for entry in bundle.ledger_entries:
        sums_by_currency[entry.currency][entry.category] += entry.amount
    checks: list[AuditCheck] = []
    account_currencies = {row.currency for row in account.currency_accounts}
    orphan_currencies = sorted(set(sums_by_currency) - account_currencies)
    if orphan_currencies:
        checks.append(AuditCheck(
            check_id="orphan_ledger_currencies",
            status=AuditCheckStatus.FAIL,
            reason_codes=(ReasonCode.CASH_RECONCILIATION_FAIL,),
            observed_value=",".join(orphan_currencies),
        ))

    aggregate_initial = aggregate_final = Decimal("0")
    aggregate_margin = aggregate_collateral = aggregate_liabilities = Decimal("0")
    for row in account.currency_accounts:
        sums = sums_by_currency[row.currency]
        final_cash = row.initial_cash + sums[LedgerCategory.CASH_FLOW] + sums[LedgerCategory.PREMIUM] + sums[LedgerCategory.COST]
        prefix = f"{row.currency}:"
        checks.extend((
            _check(prefix + "cash_reconciliation", final_cash-row.final_cash, bundle.tolerance.absolute,
                   ReasonCode.CASH_RECONCILIATION_FAIL, row.final_cash, final_cash),
            _check(prefix + "margin_reconciliation", sums[LedgerCategory.MARGIN]-row.margin_used,
                   bundle.tolerance.absolute, ReasonCode.MARGIN_RECONCILIATION_FAIL,
                   row.margin_used, sums[LedgerCategory.MARGIN]),
            _check(prefix + "collateral_reconciliation", sums[LedgerCategory.COLLATERAL]-row.collateral_value,
                   bundle.tolerance.absolute, ReasonCode.COLLATERAL_RECONCILIATION_FAIL,
                   row.collateral_value, sums[LedgerCategory.COLLATERAL]),
            _check(prefix + "liability_reconciliation", sums[LedgerCategory.LIABILITY]-row.liabilities,
                   bundle.tolerance.absolute, ReasonCode.CASH_RECONCILIATION_FAIL,
                   row.liabilities, sums[LedgerCategory.LIABILITY]),
        ))
        rate = row.functional_fx_rate
        aggregate_initial += row.initial_cash * rate
        aggregate_final += row.final_cash * rate
        aggregate_margin += row.margin_used * rate
        aggregate_collateral += row.collateral_value * rate
        aggregate_liabilities += row.liabilities * rate

    checks.extend((
        _check("aggregate_initial_cash", aggregate_initial-account.initial_cash, bundle.tolerance.absolute,
               ReasonCode.CASH_RECONCILIATION_FAIL, account.initial_cash, aggregate_initial),
        _check("aggregate_final_cash", aggregate_final-account.final_cash, bundle.tolerance.absolute,
               ReasonCode.CASH_RECONCILIATION_FAIL, account.final_cash, aggregate_final),
        _check("aggregate_margin", aggregate_margin-account.margin_used, bundle.tolerance.absolute,
               ReasonCode.MARGIN_RECONCILIATION_FAIL, account.margin_used, aggregate_margin),
        _check("aggregate_collateral", aggregate_collateral-account.collateral_value, bundle.tolerance.absolute,
               ReasonCode.COLLATERAL_RECONCILIATION_FAIL, account.collateral_value, aggregate_collateral),
        _check("aggregate_liabilities", aggregate_liabilities-account.liabilities, bundle.tolerance.absolute,
               ReasonCode.CASH_RECONCILIATION_FAIL, account.liabilities, aggregate_liabilities),
    ))
    return checks


def _valuation_position_check(bundle: StatefulEvidenceBundle) -> AuditCheck:
    positions: dict[str, Decimal] = defaultdict(Decimal)
    valuations: dict[str, Decimal] = defaultdict(Decimal)
    for row in bundle.final_positions:
        positions[row.instrument_id] += row.quantity
    for row in bundle.valuations:
        valuations[row.instrument_id] += row.quantity
    keys = set(positions) | set(valuations)
    residual = sum(abs(positions[key]-valuations[key]) for key in keys)
    return _check("valuation_position_reconciliation", residual, bundle.tolerance.absolute,
                  ReasonCode.POSITION_RECONCILIATION_FAIL, dict(sorted(positions.items())),
                  dict(sorted(valuations.items())))

def _valuation_checks(bundle: StatefulEvidenceBundle) -> list[AuditCheck]:
    checks: list[AuditCheck] = []
    for row in bundle.valuations:
        if row.market_value is None or row.mark_price is None:
            checks.append(AuditCheck(check_id=f"mark:{row.instrument_id}", status=AuditCheckStatus.WARNING,
                reason_codes=(ReasonCode.MARK_UNAVAILABLE,)))
            continue
        expected = row.quantity * row.mark_price
        checks.append(_check(f"valuation:{row.instrument_id}", row.market_value-expected,
                             bundle.tolerance.absolute, ReasonCode.NAV_RECONCILIATION_FAIL,
                             expected, row.market_value))
        expected_functional = row.market_value * row.functional_fx_rate
        observed_functional = (
            expected_functional
            if row.functional_market_value is None
            else row.functional_market_value
        )
        checks.append(_check(f"functional_valuation:{row.instrument_id}",
                             observed_functional-expected_functional,
                             bundle.tolerance.absolute, ReasonCode.NAV_RECONCILIATION_FAIL,
                             expected_functional, observed_functional))
    return checks


def _nav_pnl_checks(bundle: StatefulEvidenceBundle) -> list[AuditCheck]:
    account = bundle.account_snapshot
    pnl = bundle.pnl_snapshot
    if pnl.quality == PnLQuality.UNAVAILABLE:
        warning = (ReasonCode.MARK_UNAVAILABLE,)
        return [
            AuditCheck(check_id="pnl_components", status=AuditCheckStatus.WARNING, reason_codes=warning),
            AuditCheck(check_id="nav_to_pnl", status=AuditCheckStatus.WARNING, reason_codes=warning),
        ]
    assert pnl.realized_pnl is not None
    assert pnl.unrealized_pnl is not None
    assert pnl.costs is not None
    assert pnl.total_pnl is not None
    reported = pnl.realized_pnl + pnl.unrealized_pnl + pnl.costs
    component = _check("pnl_components", reported-pnl.total_pnl, bundle.tolerance.absolute,
                       ReasonCode.PNL_RECONCILIATION_FAIL, pnl.total_pnl, reported)
    if any(row.market_value is None for row in bundle.valuations):
        nav = AuditCheck(check_id="nav_to_pnl", status=AuditCheckStatus.WARNING,
                         reason_codes=(ReasonCode.MARK_UNAVAILABLE,))
        return [component, nav]
    marked = sum(
        row.functional_market_value
        if row.functional_market_value is not None
        else row.market_value * row.functional_fx_rate
        for row in bundle.valuations
        if row.market_value is not None
    )
    final_nav = account.final_cash + marked + account.collateral_value - account.liabilities
    nav_pnl = final_nav - account.initial_nav - account.external_cashflows
    nav = _check("nav_to_pnl", nav_pnl-pnl.total_pnl, bundle.tolerance.absolute,
                 ReasonCode.NAV_RECONCILIATION_FAIL, pnl.total_pnl, nav_pnl)
    return [component, nav]


def _replay_checks(bundle: StatefulEvidenceBundle) -> tuple[list[AuditCheck], str]:
    sequence_valid = validate_event_sequence(bundle.replay_events)
    digest = replay_hash(bundle.replay_events)
    sequence = AuditCheck(check_id="event_sequence", status=AuditCheckStatus.PASS if sequence_valid else AuditCheckStatus.FAIL,
        reason_codes=() if sequence_valid else (ReasonCode.EVENT_SEQUENCE_INVALID,))
    match = digest == bundle.replay_checkpoint.expected_state_sha256
    replay = AuditCheck(check_id="replay_hash", status=AuditCheckStatus.PASS if match else AuditCheckStatus.FAIL,
        reason_codes=() if match else (ReasonCode.REPLAY_HASH_MISMATCH,),
        expected_value=bundle.replay_checkpoint.expected_state_sha256, observed_value=digest)
    return [sequence, replay], digest

def run_independent_audit(bundle: StatefulEvidenceBundle) -> IndependentAuditReport:
    checks = [_candidate_check(bundle)]
    checks.extend(_fill_identity_checks(bundle))
    checks.extend(_order_checks(bundle))
    checks.extend([_position_check(bundle), _dual_book_check(bundle)])
    checks.extend(_account_checks(bundle))
    checks.append(_valuation_position_check(bundle))
    checks.extend(_valuation_checks(bundle))
    checks.extend(_nav_pnl_checks(bundle))
    replay_checks, digest = _replay_checks(bundle)
    checks.extend(replay_checks)
    failures = sum(check.status == AuditCheckStatus.FAIL for check in checks)
    warnings = sum(check.status == AuditCheckStatus.WARNING for check in checks)
    status = AuditOverallStatus.FAIL if failures else AuditOverallStatus.INCOMPLETE if warnings else AuditOverallStatus.PASS
    return IndependentAuditReport(audit_id=_audit_id(bundle), context=bundle.context, overall_status=status,
        checks=tuple(checks), failure_count=failures, warning_count=warnings,
        replayed_state_sha256=digest, independent_implementation=True, production_promotion_allowed=False)
