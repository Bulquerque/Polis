from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import ArtifactEnvelope

from .base import Identifier, TimeAwareModel
from .enums import CandidateType, InstrumentType, OptionRight, OptionStyle, PositionSide, SettlementType
from .policies import ApprovedS6PolicyContext


class LifecycleLegInput(TimeAwareModel):
    leg_id: Identifier
    instrument_id: Identifier
    instrument_type: InstrumentType
    side: PositionSide
    quantity_per_candidate_unit: float
    option_style: OptionStyle = OptionStyle.NONE
    option_right: OptionRight = OptionRight.NONE
    settlement_type: SettlementType = SettlementType.NONE
    strike: float | None = Field(default=None, ge=0)
    underlying_price: float | None = Field(default=None, ge=0)
    mark_value_per_unit: float = Field(ge=0)
    intrinsic_value_per_unit: float = Field(ge=0)
    time_value_per_unit: float = Field(ge=0)
    dividend_present_value_per_unit: float | None = Field(default=None, ge=0)
    exercise_fee_per_unit: float | None = Field(default=None, ge=0)
    expiration_at: datetime | None = None
    exercise_cutoff_at: datetime | None = None
    borrow_available: bool | None = None
    exercise_supported: bool = False
    assignment_supported: bool = False
    settlement_supported: bool = True
    close_supported: bool = True
    roll_supported: bool = False
    roll_target_instrument_id: Identifier | None = None

    def _validate_option_contract(self) -> None:
        required = (
            self.strike,
            self.underlying_price,
            self.expiration_at,
            self.dividend_present_value_per_unit,
            self.exercise_fee_per_unit,
            self.borrow_available,
        )
        if any(value is None for value in required):
            raise ValueError(
                "option leg requires strike, underlying price, expiration, explicit dividend/exercise economics, and borrow availability"
            )
        if self.option_style == OptionStyle.NONE or self.option_right == OptionRight.NONE:
            raise ValueError("option leg requires style and right")
        if self.exercise_cutoff_at is not None and self.exercise_cutoff_at > self.expiration_at:
            raise ValueError("exercise cutoff after expiration")

    def _validate_non_option_contract(self) -> None:
        if self.option_style != OptionStyle.NONE or self.option_right != OptionRight.NONE:
            raise ValueError("non-option leg cannot carry option semantics")

    @model_validator(mode="after")
    def validate_option_fields(self) -> "LifecycleLegInput":
        if self.instrument_type == InstrumentType.OPTION:
            self._validate_option_contract()
        else:
            self._validate_non_option_contract()
        if self.roll_supported and self.roll_target_instrument_id is None:
            raise ValueError("roll-supported leg requires roll target")
        return self


class CandidateLifecycleInput(TimeAwareModel):
    candidate_id: Identifier
    candidate_type: CandidateType
    legs: tuple[LifecycleLegInput, ...] = ()

    @model_validator(mode="after")
    def validate_structure(self) -> "CandidateLifecycleInput":
        if self.candidate_type == CandidateType.OPTION_STRUCTURE:
            if not self.legs or not any(x.instrument_type == InstrumentType.OPTION for x in self.legs):
                raise ValueError("option structure requires at least one option leg")
        elif self.legs:
            raise ValueError("linear candidate lifecycle context must not include legs")
        leg_ids = [x.leg_id for x in self.legs]
        if len(leg_ids) != len(set(leg_ids)):
            raise ValueError("duplicate lifecycle leg IDs")
        return self


class EmergencyState(TimeAwareModel):
    required_margin_relief: float = Field(default=0, ge=0)
    required_capital_relief: float = Field(default=0, ge=0)
    required_maximum_loss_relief: float = Field(default=0, ge=0)
    forced_liquidation_required: bool = False
    trigger_reason_codes: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def valid_trigger(self) -> "EmergencyState":
        required = self.required_margin_relief + self.required_capital_relief + self.required_maximum_loss_relief
        if self.forced_liquidation_required and required <= 0:
            raise ValueError("forced liquidation requires a positive relief target")
        return self


class RiskLifecycleContextPayload(TimeAwareModel):
    decision_snapshot_hash: str
    lifecycle_candidates: tuple[CandidateLifecycleInput, ...]
    emergency_state: EmergencyState
    policy_context: ApprovedS6PolicyContext

    @model_validator(mode="after")
    def unique_candidates(self) -> "RiskLifecycleContextPayload":
        ids = [x.candidate_id for x in self.lifecycle_candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate lifecycle candidate IDs")
        return self


class RiskLifecycleContextBundle(TimeAwareModel):
    envelope: ArtifactEnvelope
    payload: RiskLifecycleContextPayload
