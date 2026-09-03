from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from .base import (
    ArtifactId,
    FiniteDecimal,
    NonEmptyStr,
    ReasonCode,
    Sha256Hex,
    StrictModel,
    UtcDateTime,
)
from .integrity import IntegrityEnvelope


class ReplayEventType(StrEnum):
    ORDER_ACCEPTED = "ORDER_ACCEPTED"
    ORDER_REJECTED = "ORDER_REJECTED"
    FILL = "FILL"
    FEE = "FEE"
    MARK = "MARK"
    MARGIN_UPDATE = "MARGIN_UPDATE"
    CASH_ADJUSTMENT = "CASH_ADJUSTMENT"
    SETTLEMENT = "SETTLEMENT"


class ReplayEvent(StrictModel):
    event_id: NonEmptyStr
    sequence: int = Field(ge=0)
    occurred_at: UtcDateTime
    event_type: ReplayEventType
    order_id: NonEmptyStr | None = None
    fill_id: NonEmptyStr | None = None
    position_id: NonEmptyStr | None = None
    candidate_id: NonEmptyStr | None = None
    instrument_id: NonEmptyStr | None = None
    quantity_delta: FiniteDecimal = Decimal("0")
    price: FiniteDecimal | None = None
    contract_multiplier: FiniteDecimal = Decimal("1")
    fee_amount: FiniteDecimal = Decimal("0")
    cash_amount: FiniteDecimal | None = None
    margin_used: FiniteDecimal | None = None
    mark_price: FiniteDecimal | None = None
    settlement_cash: FiniteDecimal | None = None

    @model_validator(mode="after")
    def validate_event_fields(self) -> "ReplayEvent":
        if self.contract_multiplier <= 0:
            raise ValueError("contract_multiplier must be positive")
        if self.fee_amount < 0:
            raise ValueError("fee_amount must be non-negative")
        if self.event_type is ReplayEventType.FILL:
            required = (self.fill_id, self.position_id, self.candidate_id, self.instrument_id)
            if any(value is None for value in required) or self.price is None:
                raise ValueError("FILL requires fill/position/candidate/instrument IDs and price")
            if self.quantity_delta == 0:
                raise ValueError("FILL quantity_delta cannot be zero")
        elif self.event_type is ReplayEventType.FEE:
            if self.fee_amount <= 0:
                raise ValueError("FEE requires positive fee_amount")
        elif self.event_type is ReplayEventType.MARK:
            if self.position_id is None or self.mark_price is None:
                raise ValueError("MARK requires position_id and mark_price")
        elif self.event_type is ReplayEventType.MARGIN_UPDATE:
            if self.margin_used is None or self.margin_used < 0:
                raise ValueError("MARGIN_UPDATE requires non-negative margin_used")
        elif self.event_type is ReplayEventType.CASH_ADJUSTMENT:
            if self.cash_amount is None:
                raise ValueError("CASH_ADJUSTMENT requires cash_amount")
        elif self.event_type is ReplayEventType.SETTLEMENT:
            if self.position_id is None or self.settlement_cash is None:
                raise ValueError("SETTLEMENT requires position_id and settlement_cash")
        return self


class OrderedEventLedgerPayload(StrictModel):
    ledger_id: ArtifactId
    events: tuple[ReplayEvent, ...]

    @model_validator(mode="after")
    def validate_events(self) -> "OrderedEventLedgerPayload":
        ids = [event.event_id for event in self.events]
        sequences = [event.sequence for event in self.events]
        if len(ids) != len(set(ids)):
            raise ValueError("event IDs must be unique")
        if len(sequences) != len(set(sequences)):
            raise ValueError("event sequences must be unique")
        return self


class OrderedEventLedger(StrictModel):
    payload: OrderedEventLedgerPayload
    integrity: IntegrityEnvelope


class PositionState(StrictModel):
    position_id: NonEmptyStr
    candidate_id: NonEmptyStr
    instrument_id: NonEmptyStr
    quantity: FiniteDecimal
    mark_price: FiniteDecimal
    contract_multiplier: FiniteDecimal = Decimal("1")


class ReplayState(StrictModel):
    as_of: UtcDateTime
    cash: FiniteDecimal
    margin_used: FiniteDecimal = Decimal("0")
    fees_paid: FiniteDecimal = Decimal("0")
    positions: tuple[PositionState, ...] = ()

    @model_validator(mode="after")
    def validate_positions(self) -> "ReplayState":
        ids = [position.position_id for position in self.positions]
        if len(ids) != len(set(ids)):
            raise ValueError("position IDs must be unique")
        if self.margin_used < 0 or self.fees_paid < 0:
            raise ValueError("margin_used and fees_paid must be non-negative")
        return self

    @property
    def nav(self) -> Decimal:
        market_value = sum(
            position.quantity * position.mark_price * position.contract_multiplier
            for position in self.positions
        )
        return self.cash + market_value


class ReplayCheckpointPayload(StrictModel):
    checkpoint_id: ArtifactId
    last_sequence: int = Field(ge=-1)
    state: ReplayState


class ReplayCheckpoint(StrictModel):
    payload: ReplayCheckpointPayload
    integrity: IntegrityEnvelope


class ReplayPolicy(StrictModel):
    require_contiguous_sequence: bool = True
    accounting_tolerance: FiniteDecimal = Decimal("0.000001")
    allow_numerical_equivalence: bool = True

    @model_validator(mode="after")
    def validate_tolerance(self) -> "ReplayPolicy":
        if self.accounting_tolerance < 0:
            raise ValueError("accounting_tolerance must be non-negative")
        return self


class ReplayDifference(StrictModel):
    field: NonEmptyStr
    expected: NonEmptyStr
    observed: NonEmptyStr
    absolute_difference: FiniteDecimal | None = None
    reason_code: ReasonCode


class ReplayIntegrityStatus(StrEnum):
    REPLAY_EXACT = "REPLAY_EXACT"
    REPLAY_NUMERICALLY_EQUIVALENT = "REPLAY_NUMERICALLY_EQUIVALENT"
    REPLAY_DIVERGED = "REPLAY_DIVERGED"
    CHECKPOINT_INVALID = "CHECKPOINT_INVALID"
    EVENT_STREAM_INVALID = "EVENT_STREAM_INVALID"


class ReplayIntegrityReport(StrictModel):
    status: ReplayIntegrityStatus
    event_count: int = Field(ge=0)
    reconstructed_state: ReplayState | None
    expected_state: ReplayState | None
    differences: tuple[ReplayDifference, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()


class ReconstructedStateHashPanel(StrictModel):
    checkpoint_sha256: Sha256Hex
    event_ledger_sha256: Sha256Hex
    reconstructed_state_sha256: Sha256Hex | None
    expected_state_sha256: Sha256Hex | None


class ReplayExceptionRecord(StrictModel):
    event_id: NonEmptyStr | None
    sequence: int | None
    reason_code: ReasonCode
    message: NonEmptyStr


class ReplayExceptionPanel(StrictModel):
    exceptions: tuple[ReplayExceptionRecord, ...] = ()
