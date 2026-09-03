from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from quant_pipeline.phase_08_portfolio_control.foundation.hashing import content_sha256

from .base_models import EquityPoint
from .enums import MarkType, ValuationStatus
from .errors import ValuationIntegrityError
from .input_models import S8InputBundle
from .registry import instrument_registry
from .state_models import AccountingBundle, PositionLifecycleBundle
from .valuation_models import (
    CandidateValuation,
    DrawdownRecord,
    MarkRecord,
    NAVRecord,
    PositionValuation,
    ValuationBundle,
)

MODULE_ID = "P8.S8.M05"


def _fx_map(value: S8InputBundle) -> dict[str, Decimal]:
    result = {value.prior_state.functional_currency: Decimal("1")}
    for item in value.marks.fx_rates:
        if item.available_at > value.valuation_time:
            continue
        if item.functional_currency != value.prior_state.functional_currency:
            raise ValuationIntegrityError("FX functional currency mismatch")
        if item.currency in result and result[item.currency] != item.rate:
            raise ValuationIntegrityError(f"duplicate inconsistent FX rate: {item.currency}")
        result[item.currency] = item.rate
    return result


def _select_mark(value: S8InputBundle, instrument_id: str) -> tuple[MarkRecord | None, bool]:
    policy = value.policies.mark_selection
    candidates = [
        mark for mark in value.marks.marks
        if mark.instrument_id == instrument_id and mark.available_at <= value.valuation_time
    ]
    candidates.sort(key=lambda item: (item.available_at, item.mark_id), reverse=True)
    for mark_type in policy.preferred_types:
        if mark_type == MarkType.MODEL and not policy.allow_model:
            continue
        for mark in candidates:
            if mark.mark_type != mark_type:
                continue
            age = int((value.valuation_time - mark.available_at).total_seconds())
            if age > policy.stale_after_seconds and not policy.allow_stale:
                continue
            return mark, age > policy.stale_after_seconds
    return None, False


def _convert(amount: Decimal, currency: str, fx: dict[str, Decimal]) -> Decimal | None:
    rate = fx.get(currency)
    return None if rate is None else amount * rate


def _account_component(accounting: AccountingBundle, fx: dict[str, Decimal]) -> tuple[Decimal, tuple[str, ...]]:
    total = Decimal("0")
    missing: list[str] = []
    for account in accounting.accounts:
        raw = account.cash_available + account.collateral_restricted - account.liabilities
        converted = _convert(raw, account.currency, fx)
        if converted is None and raw != 0:
            missing.append(f"FX:{account.currency}")
        elif converted is not None:
            total += converted
    return total, tuple(missing)


def _position_valuations(value, positions, fx, registry):
    physical: list[PositionValuation] = []
    candidate: list[CandidateValuation] = []
    known = Decimal("0")
    unpriced: list[str] = []
    degraded = False
    selected: dict[str, MarkRecord | None] = {}
    for position in positions.physical_positions:
        spec = registry[position.instrument_id]
        mark, stale = _select_mark(value, position.instrument_id)
        selected[position.instrument_id] = mark
        if mark is None or mark.price is None:
            unpriced.append(position.instrument_id)
            physical.append(PositionValuation(
                instrument_id=position.instrument_id, as_of_time=value.valuation_time,
                currency=spec.currency, quantity=position.quantity, mark_type=MarkType.UNAVAILABLE,
                mark_price=None, market_value=None, signed_cost_basis=position.signed_cost_basis,
                unrealized_pnl=None, mark_age_seconds=None,
            ))
            continue
        age = int((value.valuation_time - mark.available_at).total_seconds())
        effective_type = MarkType.STALE if stale else mark.mark_type
        market_value = position.quantity * mark.price * spec.contract_multiplier
        converted = _convert(market_value, spec.currency, fx)
        if converted is None:
            unpriced.append(f"FX:{spec.currency}:{position.instrument_id}")
        else:
            known += converted
        degraded = degraded or stale or mark.mark_type == MarkType.MODEL
        physical.append(PositionValuation(
            instrument_id=position.instrument_id, as_of_time=value.valuation_time,
            currency=spec.currency, quantity=position.quantity, mark_type=effective_type,
            mark_price=mark.price, market_value=market_value,
            signed_cost_basis=position.signed_cost_basis,
            unrealized_pnl=market_value-position.signed_cost_basis,
            mark_age_seconds=age,
        ))
    for item in positions.virtual_positions:
        spec = registry[item.instrument_id]
        mark = selected.get(item.instrument_id)
        if item.instrument_id not in selected:
            mark, _ = _select_mark(value, item.instrument_id)
            selected[item.instrument_id] = mark
        market_value = None if mark is None or mark.price is None else item.quantity*mark.price*spec.contract_multiplier
        candidate.append(CandidateValuation(
            candidate_id=item.candidate_id, instrument_id=item.instrument_id,
            as_of_time=value.valuation_time, currency=spec.currency, quantity=item.quantity,
            market_value=market_value, signed_cost_basis=item.signed_cost_basis,
            unrealized_pnl=None if market_value is None else market_value-item.signed_cost_basis,
        ))
    return tuple(physical), tuple(candidate), known, tuple(sorted(set(unpriced))), degraded


def _drawdown(curve: tuple[EquityPoint, ...]) -> DrawdownRecord | None:
    if not curve:
        return None
    peak = max(point.nav for point in curve)
    current = curve[-1]
    amount = current.nav - peak
    fraction = amount / peak if peak != 0 else Decimal("0")
    return DrawdownRecord(
        as_of_time=current.as_of_time, peak_nav=peak, current_nav=current.nav,
        drawdown_amount=amount, drawdown_fraction=fraction,
    )


def execute(value: S8InputBundle, positions: PositionLifecycleBundle, accounting: AccountingBundle) -> ValuationBundle:
    registry = instrument_registry(value)
    fx = _fx_map(value)
    account_known, account_missing = _account_component(accounting, fx)
    physical, candidate, position_known, position_missing, degraded = _position_valuations(
        value, positions, fx, registry
    )
    missing = tuple(sorted(set(account_missing + position_missing)))
    known_nav = account_known + position_known
    total_nav = None if missing else known_nav
    status = ValuationStatus.INCOMPLETE if missing else ValuationStatus.DEGRADED if degraded else ValuationStatus.COMPLETE
    net_flow = value.prior_state.net_external_flow_since_open + accounting.external_flow_delta
    period_pnl = None if total_nav is None else total_nav - value.prior_state.opening_nav_functional - net_flow
    nav = NAVRecord(
        as_of_time=value.valuation_time,
        functional_currency=value.prior_state.functional_currency,
        status=status,
        total_nav=total_nav,
        known_nav_component=known_nav,
        unpriced_instruments=missing,
        net_external_flow=net_flow,
        period_pnl=period_pnl,
    )
    curve = value.prior_state.equity_curve
    if total_nav is not None:
        point = EquityPoint(as_of_time=value.valuation_time, nav=total_nav)
        curve = tuple(item for item in curve if item.as_of_time != point.as_of_time) + (point,)
        curve = tuple(sorted(curve, key=lambda item: item.as_of_time))
    payload = {
        "positions": physical,
        "candidates": candidate,
        "nav": nav,
        "equity_curve": curve,
        "drawdown": _drawdown(curve),
    }
    return ValuationBundle(**payload, content_sha256=content_sha256(payload))
