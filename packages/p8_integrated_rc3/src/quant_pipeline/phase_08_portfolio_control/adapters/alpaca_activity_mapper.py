from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from pydantic import Field

from ..foundation.errors import UnsupportedMappingError
from ..foundation.models import NonEmptyStr, StrictModel
from ..subphases.s08_stateful_engine.accounting_models import CashAdjustmentEvent, FeeEvent
from ..subphases.s08_stateful_engine.enums import CashAdjustmentType
from ..subphases.s08_stateful_engine.lifecycle_models import (
    LifecycleCandidateAllocation,
    OptionAssignmentEvent,
    OptionCashSettlementEvent,
    OptionExerciseEvent,
    OptionExpirationEvent,
    SplitEvent,
)

_FEE_TYPES = {"FEE", "REG", "TAF", "ORF", "OCC", "NRV", "NRC", "LCT"}


class AlpacaActivityContext(StrictModel):
    instrument_id: NonEmptyStr | None = None
    currency: NonEmptyStr = "USD"
    candidate_allocations: tuple[LifecycleCandidateAllocation, ...] = ()
    contract_quantity: Decimal | None = Field(default=None, gt=0)
    split_ratio_numerator: Decimal | None = Field(default=None, gt=0)
    split_ratio_denominator: Decimal | None = Field(default=None, gt=0)


def _required(payload: Mapping[str, Any], name: str) -> Any:
    value = payload.get(name)
    if value is None or value == "":
        raise UnsupportedMappingError(f"Alpaca activity missing required field: {name}")
    return value


def _event_id(payload: Mapping[str, Any]) -> str:
    return str(payload.get("event_ulid") or payload.get("id") or _required(payload, "event_id"))


def _time(payload: Mapping[str, Any]) -> datetime:
    raw = str(_required(payload, "at"))
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UnsupportedMappingError(f"invalid Alpaca activity timestamp: {raw}") from exc


def _decimal(payload: Mapping[str, Any], name: str, *, absolute: bool = False) -> Decimal:
    try:
        value = Decimal(str(_required(payload, name)))
    except (InvalidOperation, ValueError) as exc:
        raise UnsupportedMappingError(f"invalid Alpaca decimal field: {name}") from exc
    return abs(value) if absolute else value


def _reject_revision(payload: Mapping[str, Any]) -> None:
    if payload.get("previous_id") or payload.get("replaces") or payload.get("reversal_of"):
        raise UnsupportedMappingError(
            "Alpaca correction/bust requires a compensating-event adapter; capability unavailable"
        )
    status = str(payload.get("status", "executed")).lower()
    if status not in {"executed", "complete", "completed"}:
        raise UnsupportedMappingError(f"Alpaca activity is not final: {status}")


def _lifecycle_common(payload: Mapping[str, Any], context: AlpacaActivityContext):
    if context.instrument_id is None or context.contract_quantity is None:
        raise UnsupportedMappingError("option activity requires instrument_id and contract_quantity context")
    if not context.candidate_allocations:
        raise UnsupportedMappingError("option activity requires candidate attribution context")
    event_time = _time(payload)
    return dict(
        event_id=_event_id(payload), event_time=event_time, available_at=event_time,
        instrument_id=context.instrument_id, contract_quantity=context.contract_quantity,
        candidate_allocations=context.candidate_allocations,
    )


def map_activity(payload: Mapping[str, Any], context: AlpacaActivityContext):
    """Map a final Alpaca Broker activity into a canonical S8 event.

    Network access, SSE cursor management, polling and symbol resolution are deliberately outside
    this mapper. Candidate attribution and split ratios must come from reconciled portfolio state.
    """
    _reject_revision(payload)
    entry_type = str(_required(payload, "entry_type")).upper()
    common = _lifecycle_common(payload, context) if entry_type in {"OPEXC", "OPASN", "OPEXP", "OPCSH"} else None
    if entry_type == "OPEXC":
        return OptionExerciseEvent(**common)
    if entry_type == "OPASN":
        return OptionAssignmentEvent(**common)
    if entry_type == "OPEXP":
        return OptionExpirationEvent(**common)
    if entry_type == "OPCSH":
        return OptionCashSettlementEvent(
            **common, cash_amount=_decimal(payload, "net_amount"), currency=context.currency,
        )
    event_time = _time(payload)
    if entry_type == "SPLIT":
        if context.instrument_id is None or context.split_ratio_numerator is None or context.split_ratio_denominator is None:
            raise UnsupportedMappingError("split activity requires instrument and explicit reconciled ratio")
        return SplitEvent(
            event_id=_event_id(payload), event_time=event_time, available_at=event_time,
            instrument_id=context.instrument_id,
            ratio_numerator=context.split_ratio_numerator,
            ratio_denominator=context.split_ratio_denominator,
        )
    if entry_type in {"DIV", "INT"}:
        amount = _decimal(payload, "net_amount")
        adjustment = CashAdjustmentType.DIVIDEND if entry_type == "DIV" else CashAdjustmentType.INTEREST
        return CashAdjustmentEvent(
            event_id=_event_id(payload), event_time=event_time, available_at=event_time,
            currency=context.currency, amount=amount, adjustment_type=adjustment,
            reason_code=f"ALPACA_{entry_type}",
        )
    if entry_type in _FEE_TYPES or entry_type.endswith("FEE"):
        amount = _decimal(payload, "net_amount", absolute=True)
        return FeeEvent(
            event_id=_event_id(payload), event_time=event_time, available_at=event_time,
            currency=context.currency, amount=amount, fee_type=f"ALPACA_{entry_type}",
            reason_code="ALPACA_FEE_ACTIVITY",
        )
    raise UnsupportedMappingError(f"unsupported Alpaca activity type: {entry_type}")
