"""P6 candidate economics contract consumed by P8."""

from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import Field, model_validator

from .base import AwareDatetime, CurrencyCode, NonEmptyStr, StrictModel
from .common import ArtifactReference
from .enums import ComponentQualificationStatus, ExerciseStyle, PositionSide, SettlementType


class CandidateLegV1(StrictModel):
    instrument_id: NonEmptyStr
    instrument_type: NonEmptyStr
    side: PositionSide
    unit_quantity: Decimal
    contract_multiplier: Decimal = Field(gt=0)
    strike: Decimal | None = None
    expiration: AwareDatetime | None = None
    exercise_style: ExerciseStyle = ExerciseStyle.NONE
    settlement_type: SettlementType
    contract_valid_from: AwareDatetime
    contract_valid_until: AwareDatetime
    instrument_master_ref: ArtifactReference

    @model_validator(mode="after")
    def validate_leg(self) -> Self:
        if self.unit_quantity == 0:
            raise ValueError("unit_quantity must be non-zero")
        if self.contract_valid_from > self.contract_valid_until:
            raise ValueError("contract_valid_from must not exceed contract_valid_until")
        if self.exercise_style is not ExerciseStyle.NONE and self.expiration is None:
            raise ValueError("option-like legs require expiration")
        return self


class UnitEconomicsV1(StrictModel):
    entry_cost_status: ComponentQualificationStatus
    payoff_status: ComponentQualificationStatus
    maximum_loss_status: ComponentQualificationStatus
    liquidity_status: ComponentQualificationStatus
    lifecycle_status: ComponentQualificationStatus
    unit_entry_cost: Decimal | None = None
    unit_maximum_loss: Decimal | None = Field(default=None, ge=0)
    margin_per_unit: Decimal | None = Field(default=None, ge=0)
    liquidity_capacity_units: Decimal | None = Field(default=None, ge=0)
    scenario_valuation_ref: ArtifactReference | None = None

    @model_validator(mode="after")
    def validate_qualified_values(self) -> Self:
        usable = {ComponentQualificationStatus.QUALIFIED, ComponentQualificationStatus.DEGRADED}
        if self.entry_cost_status in usable and self.unit_entry_cost is None:
            raise ValueError("qualified/degraded entry cost requires unit_entry_cost")
        if self.maximum_loss_status in usable and self.unit_maximum_loss is None:
            raise ValueError("qualified/degraded maximum loss requires unit_maximum_loss")
        if self.liquidity_status in usable and self.liquidity_capacity_units is None:
            raise ValueError("qualified/degraded liquidity requires liquidity_capacity_units")
        return self


class P6CandidateEconomicPackageV1(StrictModel):
    candidate_id: NonEmptyStr
    canonical_candidate_id: NonEmptyStr
    candidate_family: NonEmptyStr
    objective_family: NonEmptyStr
    unit_definition: NonEmptyStr
    currency: CurrencyCode
    lot_size: Decimal = Field(gt=0)
    quantity_increment: Decimal = Field(gt=0)
    legs: tuple[CandidateLegV1, ...] = Field(min_length=1)
    unit_economics: UnitEconomicsV1
    p5_belief_bundle_ref: ArtifactReference
    lineage_refs: tuple[ArtifactReference, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_unique_leg_identity(self) -> Self:
        keys = [
            (
                leg.instrument_id,
                leg.side,
                leg.expiration,
                leg.strike,
                leg.settlement_type,
            )
            for leg in self.legs
        ]
        if len(set(keys)) != len(keys):
            raise ValueError("candidate legs contain duplicate canonical identities")
        return self
