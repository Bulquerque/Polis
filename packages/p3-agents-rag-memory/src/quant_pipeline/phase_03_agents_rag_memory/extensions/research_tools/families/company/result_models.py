"""Generic evidence-rich result contracts for P3.S38."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, JsonValue

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import ContractModel, NonEmptyStr, Sha256

from .model_base import CompanyMode, NonNegativeInt, OutcomeStatus, Probability, SCHEMA_VERSION, TOOL_ID


class EvidenceReference(ContractModel):
    evidence_id: NonEmptyStr
    source_id: NonEmptyStr
    p2_artifact_id: NonEmptyStr
    p2_record_id: NonEmptyStr
    available_at: datetime
    content_hash: Sha256
    source_quality: Probability = 1.0


class OperationCoverage(ContractModel):
    score: Probability
    records_requested: NonNegativeInt
    records_used: NonNegativeInt
    records_rejected_future: NonNegativeInt
    records_rejected_quality: NonNegativeInt = 0
    missing_requirements: tuple[NonEmptyStr, ...] = ()


class CompanyOperationResult(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    tool_id: Literal[TOOL_ID] = TOOL_ID
    operation_id: NonEmptyStr
    requested_mode: CompanyMode
    executed_mode: CompanyMode
    outcome_status: OutcomeStatus
    method_id: NonEmptyStr
    method_version: NonEmptyStr = "1.0.0"
    downgrade_reason: str | None = None
    metrics: dict[str, JsonValue] = Field(default_factory=dict)
    records: tuple[dict[str, JsonValue], ...] = ()
    evidence_refs: tuple[EvidenceReference, ...] = ()
    coverage: OperationCoverage
    latest_available_at: datetime | None = None
    reason_codes: tuple[NonEmptyStr, ...] = ()
    diagnostics: tuple[NonEmptyStr, ...] = ()
    cost_units: NonNegativeInt = 1
    result_hash: Sha256
