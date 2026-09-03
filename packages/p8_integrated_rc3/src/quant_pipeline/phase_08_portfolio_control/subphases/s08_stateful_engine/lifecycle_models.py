from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from quant_pipeline.phase_08_portfolio_control.foundation.models import NonEmptyStr, PositiveDecimal, TimeAwareModel
from .base_models import SignedDecimal
from .enums import ExerciseStyle, LifecycleEventType, OptionType, SettlementType


class OptionContractSpec(TimeAwareModel):
    instrument_id: NonEmptyStr
    underlying_id: NonEmptyStr
    option_type: OptionType
    strike: PositiveDecimal
    expiration: datetime
    exercise_style: ExerciseStyle
    settlement_type: SettlementType
    contract_multiplier: PositiveDecimal
    currency: NonEmptyStr


class LifecycleCandidateAllocation(TimeAwareModel):
    candidate_id: NonEmptyStr
    instrument_id: NonEmptyStr
    signed_contract_quantity: SignedDecimal
    event_time: datetime


class _OptionLifecycleBase(TimeAwareModel):
    event_id: NonEmptyStr
    event_time: datetime
    available_at: datetime
    instrument_id: NonEmptyStr
    contract_quantity: PositiveDecimal
    candidate_allocations: tuple[LifecycleCandidateAllocation, ...]

    @model_validator(mode="after")
    def validate_clocks(self):
        if self.available_at < self.event_time:
            raise ValueError("available_at cannot precede event_time")
        return self


class OptionExerciseEvent(_OptionLifecycleBase):
    event_type: Literal[LifecycleEventType.EXERCISE] = LifecycleEventType.EXERCISE


class OptionAssignmentEvent(_OptionLifecycleBase):
    event_type: Literal[LifecycleEventType.ASSIGNMENT] = LifecycleEventType.ASSIGNMENT


class OptionExpirationEvent(_OptionLifecycleBase):
    event_type: Literal[LifecycleEventType.EXPIRATION] = LifecycleEventType.EXPIRATION


class OptionCashSettlementEvent(_OptionLifecycleBase):
    event_type: Literal[LifecycleEventType.CASH_SETTLEMENT] = LifecycleEventType.CASH_SETTLEMENT
    cash_amount: SignedDecimal
    currency: NonEmptyStr


class SplitEvent(TimeAwareModel):
    event_type: Literal[LifecycleEventType.SPLIT] = LifecycleEventType.SPLIT
    event_id: NonEmptyStr
    event_time: datetime
    available_at: datetime
    instrument_id: NonEmptyStr
    ratio_numerator: PositiveDecimal
    ratio_denominator: PositiveDecimal

    @model_validator(mode="after")
    def validate_clocks(self):
        if self.available_at < self.event_time:
            raise ValueError("available_at cannot precede event_time")
        return self


LifecycleEvent = Annotated[
    Union[OptionExerciseEvent, OptionAssignmentEvent, OptionExpirationEvent, OptionCashSettlementEvent, SplitEvent],
    Field(discriminator="event_type"),
]
