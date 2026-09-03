
"""Ordinal-only preference templates compiled from P7 ranking evidence."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, model_validator

from quant_pipeline.phase_08_contracts.base import NonEmptyStr, SHA256Str, StrictModel

from .enums import ConfidenceEvidenceState, OrdinalConstraintType, PairwiseMode


class PairwiseOrdinalConstraint(StrictModel):
    constraint_id: NonEmptyStr
    constraint_type: OrdinalConstraintType
    comparison_group_id: NonEmptyStr
    preferred_candidate_id: NonEmptyStr
    less_preferred_candidate_id: NonEmptyStr
    preferred_rank: int = Field(ge=1, strict=True)
    less_preferred_rank: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.preferred_candidate_id == self.less_preferred_candidate_id:
            raise ValueError("ordinal constraint candidates must differ")
        if self.preferred_rank >= self.less_preferred_rank:
            raise ValueError("preferred rank must be numerically lower")
        return self


class LexicographicTier(StrictModel):
    comparison_group_id: NonEmptyStr
    rank: int = Field(ge=1, strict=True)
    candidate_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)


class OrdinalPenaltyTemplate(StrictModel):
    constraint_id: NonEmptyStr
    inversion_unit_penalty: Decimal = Field(default=Decimal("1"), gt=0)
    economic_weight_status: Literal["UNASSIGNED_BY_S2"] = "UNASSIGNED_BY_S2"


class ConfidenceEvidenceHint(StrictModel):
    candidate_id: NonEmptyStr
    state: ConfidenceEvidenceState
    calibration_artifact_hash: SHA256Str | None = None
    numerical_cap_status: Literal["NOT_DERIVED_BY_S2"] = "NOT_DERIVED_BY_S2"


class OrdinalSemanticsProof(StrictModel):
    pairwise_mode: PairwiseMode
    score_values_ignored: Literal[True] = True
    cardinal_financial_outputs_absent: Literal[True] = True
    scenario_distribution_unchanged: Literal[True] = True
    cross_group_constraints_absent: Literal[True] = True


class OrdinalPreferenceConstraintSet(StrictModel):
    contract_version: Literal["P8_ORDINAL_PREFERENCE_CONSTRAINT_SET_V1"]
    schema_version: Literal["1.0.0"]
    snapshot_id: NonEmptyStr
    pairwise_constraints: tuple[PairwiseOrdinalConstraint, ...]
    lexicographic_tiers: tuple[LexicographicTier, ...]
    penalty_templates: tuple[OrdinalPenaltyTemplate, ...]
    confidence_hints: tuple[ConfidenceEvidenceHint, ...]
    proof: OrdinalSemanticsProof
    reason_codes: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    content_sha256: SHA256Str

    @model_validator(mode="after")
    def validate_penalties(self) -> Self:
        constraint_ids = {row.constraint_id for row in self.pairwise_constraints}
        penalty_ids = {row.constraint_id for row in self.penalty_templates}
        if constraint_ids != penalty_ids:
            raise ValueError("every pairwise constraint must have exactly one penalty template")
        return self
