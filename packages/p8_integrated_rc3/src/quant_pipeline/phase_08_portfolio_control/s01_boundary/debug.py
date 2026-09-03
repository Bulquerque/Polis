"""Sanitized, deterministic failure bundles for S1 debugging."""

from __future__ import annotations

from pydantic import Field

from quant_pipeline.phase_08_contracts.base import AwareDatetime, NonEmptyStr, SHA256Str, StrictModel
from quant_pipeline.phase_08_contracts.enums import RuntimeMode


class S1FailureDebugBundle(StrictModel):
    module_id: NonEmptyStr
    error_type: NonEmptyStr
    reason_code: NonEmptyStr
    message: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    cycle_sequence: int = Field(ge=0, strict=True)
    decision_time: AwareDatetime
    market_cutoff_at: AwareDatetime
    computed_at: AwareDatetime
    runtime_mode: RuntimeMode
    input_hashes: tuple[SHA256Str, ...] = Field(default_factory=tuple)
