from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import Field, model_validator

from ...contracts.execution_authorization import CandidateAllocation
from ...foundation.enums import IntentType, PositionIntent, RiskRole, SecurityType, Side, StructureType, Urgency
from ...foundation.models import NonEmptyStr, NonNegativeDecimal, PositiveDecimal, StrictModel

SignedDecimal = Annotated[Decimal, Field(allow_inf_nan=False)]


class OrderIntent(StrictModel):
    intent_id: NonEmptyStr
    target_id: NonEmptyStr
    authorization_id: NonEmptyStr
    execution_group_id: NonEmptyStr
    instrument_id: NonEmptyStr
    security_type: SecurityType
    intent_type: IntentType
    position_intent: PositionIntent
    side: Side
    quantity: PositiveDecimal
    signed_quantity: SignedDecimal
    urgency: Urgency
    risk_role: RiskRole
    leg_priority: int = Field(ge=0)
    virtual_allocations: tuple[CandidateAllocation, ...]


class VirtualReallocation(StrictModel):
    reallocation_id: NonEmptyStr
    instrument_id: NonEmptyStr
    candidate_id: NonEmptyStr
    signed_quantity_delta: SignedDecimal
    reason_code: NonEmptyStr = "VIRTUAL_BOOK_REALLOCATION"


class OrderIntentBundle(StrictModel):
    bundle_id: NonEmptyStr
    intents: tuple[OrderIntent, ...]
    virtual_reallocations: tuple[VirtualReallocation, ...] = ()
    no_action: bool
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_no_action(self):
        if self.no_action != (not self.intents and not self.virtual_reallocations):
            raise ValueError("no_action must reflect both physical intents and virtual reallocations")
        return self


class TemporaryRiskBudget(StrictModel):
    max_temporary_notional: NonNegativeDecimal
    unwind_required: bool


class ExecutionStructurePlan(StrictModel):
    structure_id: NonEmptyStr
    execution_group_id: NonEmptyStr
    structure_type: StructureType
    intent_ids: tuple[NonEmptyStr, ...]
    venue: str | None
    sequence: tuple[NonEmptyStr, ...]
    temporary_risk_budget: TemporaryRiskBudget
    block_reason: str | None = None

    @model_validator(mode="after")
    def validate_structure(self):
        if self.structure_type == StructureType.BLOCKED and not self.block_reason:
            raise ValueError("blocked structures require block_reason")
        if self.structure_type != StructureType.BLOCKED and self.block_reason is not None:
            raise ValueError("non-blocked structures cannot have block_reason")
        return self


class ExecutionStructureBundle(StrictModel):
    structures: tuple[ExecutionStructurePlan, ...]
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
