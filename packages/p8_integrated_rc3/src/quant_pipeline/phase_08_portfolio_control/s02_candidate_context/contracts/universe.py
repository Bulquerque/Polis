
"""Static admission universe; no risk/liquidity/margin decisions live here."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from quant_pipeline.phase_08_contracts.base import NonEmptyStr, SHA256Str, StrictModel

from .enums import StaticActionState


class StaticActionDecision(StrictModel):
    candidate_id: NonEmptyStr
    state: StaticActionState
    reason_codes: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    representative_candidate_id: NonEmptyStr | None = None


class StaticUniverseConservationProof(StrictModel):
    input_candidate_count: int = Field(ge=0, strict=True)
    decision_count: int = Field(ge=0, strict=True)
    forwarded_count: int = Field(ge=0, strict=True)
    terminal_preserved_count: int = Field(ge=0, strict=True)
    excluded_count: int = Field(ge=0, strict=True)
    input_ids_hash: SHA256Str
    decision_ids_hash: SHA256Str
    equation_valid: bool


class StaticAdmissibleActionUniverse(StrictModel):
    contract_version: Literal["P8_STATIC_ADMISSIBLE_ACTION_UNIVERSE_V1"]
    schema_version: Literal["1.0.0"]
    snapshot_id: NonEmptyStr
    forwarded_candidate_ids: tuple[NonEmptyStr, ...]
    decisions: tuple[StaticActionDecision, ...]
    proof: StaticUniverseConservationProof
    content_sha256: SHA256Str

    @model_validator(mode="after")
    def validate_decisions(self) -> Self:
        ids = tuple(row.candidate_id for row in self.decisions)
        if len(set(ids)) != len(ids):
            raise ValueError("static action decisions must be unique by candidate_id")
        forwarded_from_decisions = tuple(sorted(
            row.candidate_id for row in self.decisions if row.state is StaticActionState.FORWARD_TO_RISK
        ))
        if forwarded_from_decisions != tuple(sorted(self.forwarded_candidate_ids)):
            raise ValueError("forwarded_candidate_ids must match FORWARD_TO_RISK decisions")
        return self
