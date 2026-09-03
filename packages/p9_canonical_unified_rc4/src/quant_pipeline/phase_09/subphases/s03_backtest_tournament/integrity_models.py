"""Typed P8 handoff, ledgers, and qualification outputs for P9.S3.M04."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from .common import (
    FiniteDecimal,
    NonEmptyStr,
    SemVer,
    Sha256,
    StrictModel,
    UtcDateTime,
)


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(StrEnum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class CandidateTerminalState(StrEnum):
    GENERATED = "GENERATED"
    RANKED = "RANKED"
    BLOCKED = "BLOCKED"
    ABSTAINED = "ABSTAINED"
    SELECTED = "SELECTED"
    NOT_SELECTED = "NOT_SELECTED"
    EXECUTED = "EXECUTED"
    NO_ACTION = "NO_ACTION"


class LifecycleType(StrEnum):
    EXERCISE = "EXERCISE"
    ASSIGNMENT = "ASSIGNMENT"
    EXPIRY = "EXPIRY"
    ROLL = "ROLL"
    CASH_SETTLEMENT = "CASH_SETTLEMENT"
    QUANTITY_ADJUSTMENT = "QUANTITY_ADJUSTMENT"


class CashCategory(StrEnum):
    FILL = "FILL"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    INTEREST = "INTEREST"
    FINANCING = "FINANCING"
    BORROW = "BORROW"
    LIFECYCLE = "LIFECYCLE"
    OTHER_FEE = "OTHER_FEE"


class CandidateTerminalRecord(StrictModel):
    candidate_id: NonEmptyStr
    state: CandidateTerminalState
    reason_codes: tuple[NonEmptyStr, ...] = ()


class OrderRecord(StrictModel):
    order_id: NonEmptyStr
    candidate_id: NonEmptyStr | None = None
    instrument_id: NonEmptyStr
    side: Side
    quantity: FiniteDecimal = Field(gt=Decimal("0"))
    decision_time: UtcDateTime
    available_at: UtcDateTime
    status: OrderStatus

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        if self.available_at > self.decision_time:
            raise ValueError("order inputs must be available by decision_time")
        return self


class FillRecord(StrictModel):
    fill_id: NonEmptyStr
    order_id: NonEmptyStr
    instrument_id: NonEmptyStr
    side: Side
    quantity: FiniteDecimal = Field(gt=Decimal("0"))
    price: FiniteDecimal = Field(gt=Decimal("0"))
    fee: FiniteDecimal = Field(ge=Decimal("0"))
    fill_time: UtcDateTime
    available_at: UtcDateTime

    @model_validator(mode="after")
    def validate_report_time(self) -> Self:
        if self.available_at < self.fill_time:
            raise ValueError("fill cannot be available before it occurs")
        return self


class CashLedgerEntry(StrictModel):
    entry_id: NonEmptyStr
    event_time: UtcDateTime
    amount: FiniteDecimal
    category: CashCategory
    related_fill_id: NonEmptyStr | None = None
    related_lifecycle_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_links(self) -> Self:
        if self.category is CashCategory.FILL and self.related_fill_id is None:
            raise ValueError("FILL cash entry requires related_fill_id")
        if self.category is CashCategory.LIFECYCLE and self.related_lifecycle_id is None:
            raise ValueError("LIFECYCLE cash entry requires related_lifecycle_id")
        return self


class LifecycleEvent(StrictModel):
    event_id: NonEmptyStr
    instrument_id: NonEmptyStr
    event_type: LifecycleType
    event_time: UtcDateTime
    quantity_delta: FiniteDecimal = Decimal("0")
    cash_amount: FiniteDecimal = Decimal("0")


class PositionSnapshot(StrictModel):
    instrument_id: NonEmptyStr
    quantity: FiniteDecimal
    market_value: FiniteDecimal


class ValuationRecord(StrictModel):
    valuation_time: UtcDateTime
    cash: FiniteDecimal
    market_value: FiniteDecimal
    gross_pnl: FiniteDecimal
    costs: FiniteDecimal = Field(ge=Decimal("0"))
    net_pnl: FiniteDecimal
    nav: FiniteDecimal


class P8EvaluationHandoff(StrictModel):
    handoff_id: NonEmptyStr
    schema_version: SemVer
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    trial_id: NonEmptyStr
    fold_id: NonEmptyStr
    capability: NonEmptyStr
    start_cash: FiniteDecimal
    end_cash: FiniteDecimal
    p6_candidate_ids: tuple[NonEmptyStr, ...]
    p7_terminal_records: tuple[CandidateTerminalRecord, ...]
    p8_terminal_records: tuple[CandidateTerminalRecord, ...]
    orders: tuple[OrderRecord, ...]
    fills: tuple[FillRecord, ...]
    cash_entries: tuple[CashLedgerEntry, ...]
    lifecycle_events: tuple[LifecycleEvent, ...]
    final_positions: tuple[PositionSnapshot, ...]
    valuations: tuple[ValuationRecord, ...]
    required_lifecycle_supported: bool
    replay_sha256: Sha256

    @model_validator(mode="after")
    def validate_uniqueness(self) -> Self:
        groups = {
            "p6 candidate IDs": list(self.p6_candidate_ids),
            "p7 candidate IDs": [item.candidate_id for item in self.p7_terminal_records],
            "p8 candidate IDs": [item.candidate_id for item in self.p8_terminal_records],
            "order IDs": [item.order_id for item in self.orders],
            "fill IDs": [item.fill_id for item in self.fills],
            "cash entry IDs": [item.entry_id for item in self.cash_entries],
            "lifecycle IDs": [item.event_id for item in self.lifecycle_events],
            "position instruments": [item.instrument_id for item in self.final_positions],
        }
        for name, values in groups.items():
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {name}")
        if not self.valuations:
            raise ValueError("at least one valuation record is required")
        if list(self.valuations) != sorted(self.valuations, key=lambda item: item.valuation_time):
            raise ValueError("valuations must be time-ordered")
        return self


class ReconciliationTolerance(StrictModel):
    money: FiniteDecimal = Field(default=Decimal("0.000001"), ge=Decimal("0"))
    quantity: FiniteDecimal = Field(default=Decimal("0.000001"), ge=Decimal("0"))


class CheckResult(StrictModel):
    check_id: NonEmptyStr
    passed: bool
    observed: NonEmptyStr
    expected: NonEmptyStr
    reason_code: NonEmptyStr | None = None


class QualificationState(StrEnum):
    QUALIFIED = "QUALIFIED"
    NO_ACTION_VALID = "NO_ACTION_VALID"
    INVALID = "INVALID"
    LEGACY_RESEARCH_ONLY = "LEGACY_RESEARCH_ONLY"


class BacktestQualificationReceipt(StrictModel):
    handoff_id: NonEmptyStr
    state: QualificationState
    checks: tuple[CheckResult, ...]
    reason_codes: tuple[NonEmptyStr, ...]
    qualified_handoff_sha256: Sha256 | None
    content_sha256: Sha256
