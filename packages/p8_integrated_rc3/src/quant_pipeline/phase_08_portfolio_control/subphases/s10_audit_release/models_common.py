from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from quant_pipeline.phase_08_contracts.canonical import canonical_json_bytes, canonical_sha256

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

class ArtifactRef(StrictModel):
    artifact_id: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: str = Field(min_length=1)
    contract_version: str = Field(min_length=1)
    producer_phase: str = Field(min_length=1)
    producer_module: str = Field(min_length=1)

class AuditContext(StrictModel):
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    decision_time: datetime
    audit_time: datetime
    contract_version: str = "1.0.0"
    schema_version: str = "1.0.0"
    @field_validator("decision_time", "audit_time")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value
    @field_validator("audit_time")
    @classmethod
    def audit_after_decision(cls, value: datetime, info: Any) -> datetime:
        decision = info.data.get("decision_time")
        if decision is not None and value < decision:
            raise ValueError("audit_time cannot precede decision_time")
        return value

class DecimalTolerance(StrictModel):
    absolute: Decimal = Field(default=Decimal("0.000001"), ge=0)

class ProductionLock(StrictModel):
    production_promotion_allowed: Literal[False] = False

def content_sha256(value: BaseModel | dict[str, Any] | list[Any]) -> str:
    return canonical_sha256(value)
