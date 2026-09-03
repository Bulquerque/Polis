
"""Sanitized deterministic S2 failure bundle."""

from pydantic import Field

from quant_pipeline.phase_08_contracts.base import AwareDatetime, NonEmptyStr, SHA256Str, StrictModel


class S2FailureDebugBundle(StrictModel):
    module_id: NonEmptyStr
    error_type: NonEmptyStr
    reason_code: NonEmptyStr
    message: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    decision_time: AwareDatetime
    computed_at: AwareDatetime
    input_hashes: tuple[SHA256Str, ...] = Field(default_factory=tuple)
