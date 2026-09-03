from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from quant_pipeline.phase_08_contracts.canonical import canonical_json_bytes, canonical_sha256


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ArtifactRef(StrictModel):
    artifact_id: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: str = Field(min_length=1)
    contract_version: str = Field(min_length=1)


class RuntimeContext(StrictModel):
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    decision_time: datetime
    observed_at: datetime
    policy_version: str = Field(min_length=1)

    @field_validator("decision_time", "observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value

    @field_validator("observed_at")
    @classmethod
    def observed_not_before_decision(cls, value: datetime, info: Any) -> datetime:
        decision = info.data.get("decision_time")
        if decision is not None and value < decision:
            raise ValueError("observed_at cannot precede decision_time")
        return value


class TargetQuantity(StrictModel):
    instrument_id: str = Field(min_length=1)
    quantity: Decimal


def content_sha256(model: BaseModel | dict[str, Any]) -> str:
    return canonical_sha256(model)
