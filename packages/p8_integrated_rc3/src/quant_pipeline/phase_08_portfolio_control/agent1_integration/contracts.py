"""Strict integration-only contracts; economic contracts remain owned by S1/S2."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from quant_pipeline.phase_08_contracts.base import NonEmptyStr, SHA256Str, StrictModel


class Agent1IntegrationReceiptV1(StrictModel):
    contract_version: Literal["P8_AGENT1_INTEGRATION_RECEIPT_V1"]
    schema_version: Literal["1.0.0"]
    integration_release: Literal["0.1.0"]
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    s1_snapshot_id: NonEmptyStr
    s1_snapshot_hash: SHA256Str
    s2_input_hash: SHA256Str
    s2_output_hash: SHA256Str
    received_candidate_count: int = Field(ge=0, strict=True)
    actionable_candidate_count: int = Field(ge=0, strict=True)
    forwarded_candidate_count: int = Field(ge=0, strict=True)
    no_action_valid: bool
    content_sha256: SHA256Str
