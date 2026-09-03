"""Operation result and evidence contracts for P3.S39."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Literal

from pydantic import JsonValue, field_validator, model_validator

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import ContractModel, NonEmptyStr, Sha256, utc

from .model_base import NonNegativeInt, OutcomeStatus, Probability, QuantMode, SCHEMA_VERSION, TOOL_ID


class EvidenceReference(ContractModel):
    evidence_id: NonEmptyStr
    source_id: NonEmptyStr
    p2_artifact_id: NonEmptyStr
    p2_record_id: NonEmptyStr
    available_at: datetime
    content_hash: Sha256
    source_quality: Probability = 1.0

    @field_validator("available_at")
    @classmethod
    def aware_available_at(cls, value: datetime) -> datetime:
        return utc(value)


class OperationCoverage(ContractModel):
    score: Probability
    observations_requested: NonNegativeInt
    observations_used: NonNegativeInt
    observations_rejected_future: NonNegativeInt
    observations_rejected_quality: NonNegativeInt
    missing_requirements: tuple[NonEmptyStr, ...] = ()


class QuantOperationResult(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    tool_id: Literal[TOOL_ID] = TOOL_ID
    operation_id: NonEmptyStr
    requested_mode: QuantMode
    executed_mode: QuantMode
    outcome_status: OutcomeStatus
    method_id: NonEmptyStr
    method_version: NonEmptyStr = "1.0.0"
    downgrade_reason: str | None = None
    metrics: dict[str, JsonValue]
    series: tuple[dict[str, JsonValue], ...] = ()
    evidence_refs: tuple[EvidenceReference, ...]
    coverage: OperationCoverage
    latest_available_at: datetime | None = None
    reason_codes: tuple[NonEmptyStr, ...] = ()
    diagnostics: tuple[NonEmptyStr, ...] = ()
    result_hash: Sha256

    @field_validator("latest_available_at")
    @classmethod
    def aware_latest_available_at(cls, value: datetime | None) -> datetime | None:
        return None if value is None else utc(value)

    @model_validator(mode="after")
    def numeric_outputs_are_finite(self) -> "QuantOperationResult":
        def check(value: JsonValue, path: str) -> None:
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"non-finite numeric output at {path}")
            if isinstance(value, dict):
                for key, item in value.items():
                    check(item, f"{path}.{key}")
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    check(item, f"{path}[{index}]")
        check(self.metrics, "metrics")
        for index, record in enumerate(self.series):
            check(record, f"series[{index}]")
        return self
