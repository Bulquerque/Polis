"""P8.S1.M05 — load and reconcile read-only portfolio/account state."""

from __future__ import annotations

from decimal import Decimal

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256
from quant_pipeline.phase_08_contracts.enums import (
    DiscrepancySeverity,
    ReceiptStatus,
    RuntimeMode,
    StateQualityStatus,
)
from quant_pipeline.phase_08_contracts.s1 import M05Result
from quant_pipeline.phase_08_contracts.state import (
    AccountSnapshot,
    PortfolioStateProjection,
    CurrentPortfolioAndAccountState,
    StateDiscrepancy,
    StateQualityReport,
)

from ..context import S1ExecutionContext
from ..errors import CapabilityError, HashMismatchError, StateInvariantError, TemporalIntegrityError
from ..module_support import build_receipt
from ..policies import StateReconciliationPolicy
from ..ports import AccountSnapshotPort, PortfolioStateReaderPort

MODULE_ID = "P8.S1.M05"
_HASH_EXCLUDE = frozenset({"content_sha256"})


def _verify_projection_hash(value: object, expected: str, label: str) -> None:
    actual = canonical_sha256(value, exclude_keys=_HASH_EXCLUDE)
    if actual != expected:
        raise HashMismatchError(f"{label} canonical hash mismatch: expected={expected} actual={actual}")


def _decimal_discrepancy(
    *,
    category: str,
    key: str,
    internal: Decimal | None,
    external: Decimal | None,
    tolerance: Decimal,
) -> StateDiscrepancy | None:
    if internal is None or external is None:
        if internal == external:
            return None
        return StateDiscrepancy(
            category=category,
            key=key,
            severity=DiscrepancySeverity.CRITICAL,
            internal_value="MISSING" if internal is None else str(internal),
            external_value="MISSING" if external is None else str(external),
            tolerance=tolerance,
        )
    if abs(internal - external) <= tolerance:
        return None
    return StateDiscrepancy(
        category=category,
        key=key,
        severity=DiscrepancySeverity.MATERIAL,
        internal_value=str(internal),
        external_value=str(external),
        tolerance=tolerance,
    )


def _reconcile_positions(internal: PortfolioStateProjection, external: AccountSnapshot, policy: StateReconciliationPolicy) -> list[StateDiscrepancy]:
    internal_map = {row.instrument_id: row.quantity for row in internal.positions}
    external_map = {row.instrument_id: row.quantity for row in external.positions}
    discrepancies: list[StateDiscrepancy] = []
    for key in sorted(set(internal_map) | set(external_map)):
        discrepancy = _decimal_discrepancy(
            category="POSITION_QUANTITY",
            key=key,
            internal=internal_map.get(key),
            external=external_map.get(key),
            tolerance=policy.position_quantity_tolerance,
        )
        if discrepancy is not None:
            discrepancies.append(discrepancy)
    return discrepancies


def _reconcile_cash(internal: PortfolioStateProjection, external: AccountSnapshot, policy: StateReconciliationPolicy) -> list[StateDiscrepancy]:
    internal_map = {row.currency: row.amount for row in internal.cash}
    external_map = {row.currency: row.amount for row in external.cash}
    discrepancies: list[StateDiscrepancy] = []
    for key in sorted(set(internal_map) | set(external_map)):
        discrepancy = _decimal_discrepancy(
            category="CASH_BALANCE",
            key=key,
            internal=internal_map.get(key),
            external=external_map.get(key),
            tolerance=policy.cash_tolerance,
        )
        if discrepancy is not None:
            discrepancies.append(discrepancy)
    return discrepancies


def _reconcile_margin(internal: PortfolioStateProjection, external: AccountSnapshot, policy: StateReconciliationPolicy) -> list[StateDiscrepancy]:
    internal_map = {row.currency: (row.used, row.available) for row in internal.margin}
    external_map = {row.currency: (row.used, row.available) for row in external.margin}
    discrepancies: list[StateDiscrepancy] = []
    for key in sorted(set(internal_map) | set(external_map)):
        internal_pair = internal_map.get(key)
        external_pair = external_map.get(key)
        for label, index in (("MARGIN_USED", 0), ("MARGIN_AVAILABLE", 1)):
            discrepancy = _decimal_discrepancy(
                category=label,
                key=key,
                internal=None if internal_pair is None else internal_pair[index],
                external=None if external_pair is None else external_pair[index],
                tolerance=policy.margin_tolerance,
            )
            if discrepancy is not None:
                discrepancies.append(discrepancy)
    return discrepancies


def _reconcile_collateral(
    internal: PortfolioStateProjection,
    external: AccountSnapshot,
    policy: StateReconciliationPolicy,
) -> list[StateDiscrepancy]:
    internal_map = {row.asset_id: row.eligible_value for row in internal.collateral}
    external_map = {row.asset_id: row.eligible_value for row in external.collateral}
    discrepancies: list[StateDiscrepancy] = []
    for key in sorted(set(internal_map) | set(external_map)):
        discrepancy = _decimal_discrepancy(
            category="COLLATERAL_ELIGIBLE_VALUE",
            key=key,
            internal=internal_map.get(key),
            external=external_map.get(key),
            tolerance=policy.collateral_tolerance,
        )
        if discrepancy is not None:
            discrepancies.append(discrepancy)
    return discrepancies


def _reconcile_orders(internal: PortfolioStateProjection, external: AccountSnapshot, policy: StateReconciliationPolicy) -> list[StateDiscrepancy]:
    internal_map = {row.order_id: row.remaining_quantity for row in internal.open_orders}
    external_map = {row.order_id: row.remaining_quantity for row in external.open_orders}
    discrepancies: list[StateDiscrepancy] = []
    for key in sorted(set(internal_map) | set(external_map)):
        discrepancy = _decimal_discrepancy(
            category="OPEN_ORDER_REMAINING",
            key=key,
            internal=internal_map.get(key),
            external=external_map.get(key),
            tolerance=policy.open_order_quantity_tolerance,
        )
        if discrepancy is not None:
            discrepancies.append(discrepancy)
    return discrepancies


def _quality_status(
    *,
    mode: RuntimeMode,
    external_present: bool,
    discrepancies: tuple[StateDiscrepancy, ...],
    policy: StateReconciliationPolicy,
) -> StateQualityStatus:
    if mode is RuntimeMode.BACKTEST and not external_present:
        return StateQualityStatus.USABLE_BACKTEST
    material_count = sum(
        discrepancy.severity in {DiscrepancySeverity.MATERIAL, DiscrepancySeverity.CRITICAL}
        for discrepancy in discrepancies
    )
    if material_count == 0:
        return StateQualityStatus.USABLE
    if material_count > policy.material_discrepancy_limit:
        return StateQualityStatus.BLOCKED
    return StateQualityStatus.DEGRADED


def run_module(
    *,
    portfolio_reader: PortfolioStateReaderPort,
    account_port: AccountSnapshotPort,
    context: S1ExecutionContext,
    policy: StateReconciliationPolicy,
) -> M05Result:
    portfolio = portfolio_reader.read(as_of_time=context.decision_time)
    if portfolio.as_of_time > context.decision_time:
        raise TemporalIntegrityError("portfolio state projection is from the future")
    if portfolio.event_log_ref.available_at > context.decision_time:
        raise TemporalIntegrityError("portfolio event log was unavailable at decision_time")
    if portfolio.checkpoint_ref is not None and portfolio.checkpoint_ref.available_at > context.decision_time:
        raise TemporalIntegrityError("portfolio checkpoint was unavailable at decision_time")
    _verify_projection_hash(portfolio, portfolio.content_sha256, "portfolio state")
    account = account_port.read(as_of_time=context.decision_time)
    if account is None and context.runtime_mode is not RuntimeMode.BACKTEST:
        raise CapabilityError("external account snapshot is required in SHADOW/LIVE mode")
    discrepancies: list[StateDiscrepancy] = []
    if account is not None:
        if account.as_of_time > context.decision_time:
            raise TemporalIntegrityError("account snapshot is from the future")
        _verify_projection_hash(account, account.content_sha256, "account snapshot")
        discrepancies.extend(_reconcile_positions(portfolio, account, policy))
        discrepancies.extend(_reconcile_cash(portfolio, account, policy))
        discrepancies.extend(_reconcile_margin(portfolio, account, policy))
        discrepancies.extend(_reconcile_collateral(portfolio, account, policy))
        discrepancies.extend(_reconcile_orders(portfolio, account, policy))
    discrepancy_tuple = tuple(discrepancies)
    status = _quality_status(
        mode=context.runtime_mode,
        external_present=account is not None,
        discrepancies=discrepancy_tuple,
        policy=policy,
    )
    quality = StateQualityReport(
        runtime_mode=context.runtime_mode,
        status=status,
        discrepancies=discrepancy_tuple,
        external_snapshot_present=account is not None,
        reason_codes=("STATE_RECONCILIATION_BLOCKED",) if status is StateQualityStatus.BLOCKED else (),
    )
    current = CurrentPortfolioAndAccountState(
        portfolio_state=portfolio,
        account_snapshot=account,
        quality_report=quality,
    )
    receipt = build_receipt(
        module_id=MODULE_ID,
        status=ReceiptStatus.SEMANTICALLY_CONSUMED,
        inputs=(portfolio,) if account is None else (portfolio, account),
        output=current,
        computed_at=context.computed_at,
    )
    return M05Result(current_state=current, receipt=receipt)
