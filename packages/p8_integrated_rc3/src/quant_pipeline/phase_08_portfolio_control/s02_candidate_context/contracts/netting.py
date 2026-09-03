
"""Virtual-to-physical linear transform; deliberately contains no final quantities."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, model_validator

from quant_pipeline.phase_08_contracts.base import CurrencyCode, NonEmptyStr, SHA256Str, StrictModel

from .enums import VirtualIntentState


class VirtualCandidateIntentRecord(StrictModel):
    candidate_id: NonEmptyStr
    canonical_candidate_id: NonEmptyStr
    unit_definition: NonEmptyStr
    state: VirtualIntentState


class CandidateInstrumentCoefficient(StrictModel):
    candidate_id: NonEmptyStr
    instrument_id: NonEmptyStr
    signed_contracts_per_candidate_unit: Decimal
    contract_multiplier: Decimal = Field(gt=0)
    currency: CurrencyCode

    @model_validator(mode="after")
    def validate_nonzero(self) -> Self:
        if self.signed_contracts_per_candidate_unit == 0:
            raise ValueError("netting coefficient must be non-zero")
        return self


class CurrentPhysicalPositionBaseline(StrictModel):
    instrument_id: NonEmptyStr
    current_contract_quantity: Decimal
    contract_multiplier: Decimal = Field(gt=0)
    currency: CurrencyCode
    virtual_attribution_status: Literal["UNAVAILABLE_IN_S1_STATE", "NOT_REQUIRED_ZERO_POSITION"]


class NettingTransformProof(StrictModel):
    candidate_count: int = Field(ge=0, strict=True)
    instrument_count: int = Field(ge=0, strict=True)
    coefficient_count: int = Field(ge=0, strict=True)
    all_active_candidates_mapped: bool
    contains_final_target_quantities: Literal[False] = False
    equation_semantics: Literal[
        "target_physical_quantity = current_physical_quantity + sum(coefficient * virtual_candidate_quantity)"
    ]


class NettingTransform(StrictModel):
    contract_version: Literal["P8_NETTING_TRANSFORM_V1"]
    schema_version: Literal["1.0.0"]
    snapshot_id: NonEmptyStr
    virtual_intents: tuple[VirtualCandidateIntentRecord, ...]
    coefficients: tuple[CandidateInstrumentCoefficient, ...]
    current_positions: tuple[CurrentPhysicalPositionBaseline, ...]
    proof: NettingTransformProof
    content_sha256: SHA256Str

    @model_validator(mode="after")
    def validate_mapping(self) -> Self:
        active = {row.candidate_id for row in self.virtual_intents if row.state is VirtualIntentState.ACTIVE_FOR_SIZING}
        mapped = {row.candidate_id for row in self.coefficients}
        if active != mapped:
            raise ValueError("every active virtual candidate must have at least one physical coefficient")
        if len({(row.candidate_id, row.instrument_id) for row in self.coefficients}) != len(self.coefficients):
            raise ValueError("candidate/instrument coefficients must be unique")
        return self
