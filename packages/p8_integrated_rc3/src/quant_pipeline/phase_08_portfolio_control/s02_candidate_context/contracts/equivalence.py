
"""Conservative exact/scale equivalence and soft-similarity requests."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, model_validator

from quant_pipeline.phase_08_contracts.base import NonEmptyStr, SHA256Str, StrictModel

from .enums import EquivalenceType


class EquivalenceMember(StrictModel):
    candidate_id: NonEmptyStr
    scale_factor_from_representative: Decimal = Field(gt=0)


class EquivalenceGroup(StrictModel):
    equivalence_group_id: NonEmptyStr
    equivalence_type: EquivalenceType
    representative_candidate_id: NonEmptyStr
    comparison_group_id: NonEmptyStr
    members: tuple[EquivalenceMember, ...] = Field(min_length=2)
    physical_signature_hash: SHA256Str
    hard_redundant_eligible: bool
    reason_codes: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_representative(self) -> Self:
        ids = tuple(member.candidate_id for member in self.members)
        if len(set(ids)) != len(ids):
            raise ValueError("equivalence members must be unique")
        if self.representative_candidate_id not in ids:
            raise ValueError("representative must be a group member")
        return self


class ExactEquivalenceGroupPanel(StrictModel):
    contract_version: Literal["P8_EXACT_EQUIVALENCE_GROUP_PANEL_V1"]
    schema_version: Literal["1.0.0"]
    snapshot_id: NonEmptyStr
    groups: tuple[EquivalenceGroup, ...]
    content_sha256: SHA256Str


class SoftSimilarityRequest(StrictModel):
    request_id: NonEmptyStr
    left_candidate_id: NonEmptyStr
    right_candidate_id: NonEmptyStr
    comparison_group_id: NonEmptyStr
    shared_instrument_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    shared_underlying_scope: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    requested_dimensions: tuple[NonEmptyStr, ...] = Field(min_length=1)
    exclusion_authority: Literal[False] = False


class SoftSimilarityRequestPanel(StrictModel):
    contract_version: Literal["P8_SOFT_SIMILARITY_REQUEST_PANEL_V1"]
    schema_version: Literal["1.0.0"]
    snapshot_id: NonEmptyStr
    requests: tuple[SoftSimilarityRequest, ...]
    content_sha256: SHA256Str
