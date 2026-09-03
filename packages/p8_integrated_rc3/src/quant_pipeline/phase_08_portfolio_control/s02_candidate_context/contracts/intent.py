
"""Unit-normalized candidate intent contracts."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, model_validator

from quant_pipeline.phase_08_contracts.base import CurrencyCode, NonEmptyStr, SHA256Str, StrictModel
from quant_pipeline.phase_08_contracts.enums import (
    ComponentQualificationStatus,
    ExerciseStyle,
    PositionSide,
    SettlementType,
)


class NormalizedLeg(StrictModel):
    leg_id: NonEmptyStr
    instrument_id: NonEmptyStr
    instrument_type: NonEmptyStr
    side: PositionSide
    contract_quantity_per_candidate_unit: Decimal = Field(gt=0)
    signed_contract_quantity_per_candidate_unit: Decimal
    contract_multiplier: Decimal = Field(gt=0)
    strike: Decimal | None = None
    expiration: str | None = None
    exercise_style: ExerciseStyle
    settlement_type: SettlementType
    instrument_master_hash: SHA256Str

    @model_validator(mode="after")
    def validate_signed_quantity(self) -> Self:
        expected = self.contract_quantity_per_candidate_unit
        if self.side is PositionSide.SHORT:
            expected = -expected
        if self.signed_contract_quantity_per_candidate_unit != expected:
            raise ValueError("signed quantity must be derived exclusively from side and positive magnitude")
        return self


class NormalizedUnitEconomics(StrictModel):
    entry_cost_status: ComponentQualificationStatus
    payoff_status: ComponentQualificationStatus
    maximum_loss_status: ComponentQualificationStatus
    liquidity_status: ComponentQualificationStatus
    lifecycle_status: ComponentQualificationStatus
    unit_entry_cost: Decimal | None = None
    unit_maximum_loss: Decimal | None = Field(default=None, ge=0)
    margin_per_unit: Decimal | None = Field(default=None, ge=0)
    liquidity_capacity_units: Decimal | None = Field(default=None, ge=0)


class NormalizedCandidateIntent(StrictModel):
    candidate_id: NonEmptyStr
    canonical_candidate_id: NonEmptyStr
    comparison_group_id: NonEmptyStr
    candidate_family: NonEmptyStr
    objective_family: NonEmptyStr
    unit_definition: NonEmptyStr
    currency: CurrencyCode
    lot_size: Decimal = Field(gt=0)
    quantity_increment: Decimal = Field(gt=0)
    legs: tuple[NormalizedLeg, ...] = Field(min_length=1)
    unit_economics: NormalizedUnitEconomics
    p6_package_hash: SHA256Str
    p5_belief_bundle_hash: SHA256Str
    p5_evidence_signature_hash: SHA256Str
    source_score_semantics: NonEmptyStr

    @model_validator(mode="after")
    def validate_unique_legs(self) -> Self:
        if len({leg.leg_id for leg in self.legs}) != len(self.legs):
            raise ValueError("normalized leg_id values must be unique")
        return self


class NormalizedCandidateIntentPanel(StrictModel):
    contract_version: Literal["P8_NORMALIZED_CANDIDATE_INTENT_PANEL_V1"]
    schema_version: Literal["1.0.0"]
    snapshot_id: NonEmptyStr
    candidates: tuple[NormalizedCandidateIntent, ...]
    content_sha256: SHA256Str
