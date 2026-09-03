"""Exact P4 V14.9 wire models kept outside the internal P5 domain."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum, StrEnum
from math import isfinite
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

P4_VERSION = "v14.9-rc1"
P4_PHASE = "phase_04_feature_base"
P5_PHASE = "phase_05_underlying_forecasts"


def _canonical_value(value: Any) -> Any:
    if is_dataclass(value):
        return _canonical_value(asdict(value))
    if isinstance(value, datetime):
        aware = _utc(value)
        return aware.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("non-finite floats are forbidden in canonical JSON")
        return value
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [_canonical_value(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))
    return value


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        _canonical_value(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


class P4ExecutionStatus(StrEnum):
    PRODUCED = "PRODUCED"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    SKIPPED_NOT_AVAILABLE = "SKIPPED_NOT_AVAILABLE"
    SKIPPED_NOT_AUTHORIZED = "SKIPPED_NOT_AUTHORIZED"
    UNAVAILABLE_UPSTREAM = "UNAVAILABLE_UPSTREAM"
    FAILED_NONBLOCKING = "FAILED_NONBLOCKING"
    NOT_RUN = "NOT_RUN"


class P4QualityStatus(StrEnum):
    VALIDATED = "VALIDATED"
    PASS = "PASS"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    NOT_EVALUATED = "NOT_EVALUATED"


class P4ArtifactEnvelope(BaseModel):
    """Canonical S7-S9 P4 artifact envelope."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    artifact_id: str = Field(min_length=1)
    artifact_name: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    producer_phase: str = Field(min_length=1)
    producer_module_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    created_at: datetime
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_count: int = Field(ge=0)
    grain: tuple[str, ...]
    lineage_id: str = Field(min_length=1)
    execution_status: P4ExecutionStatus
    quality_status: P4QualityStatus
    records: tuple[dict[str, Any], ...]
    metadata: dict[str, Any] = Field(default_factory=dict)
    alias_of: str | None = None

    @field_validator("as_of_time", "created_at")
    @classmethod
    def aware_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_envelope(self) -> "P4ArtifactEnvelope":
        if self.producer_phase != P4_PHASE:
            raise ValueError("P4 artifact producer_phase is invalid")
        if self.schema_version.lower() != P4_VERSION:
            raise ValueError(f"unsupported P4 schema_version: {self.schema_version}")
        if self.created_at < self.as_of_time:
            raise ValueError("P4 artifact created_at cannot precede as_of_time")
        if self.record_count != len(self.records):
            raise ValueError("P4 artifact record_count differs from records")
        expected = canonical_sha256(
            {"records": self.records, "metadata": self.metadata, "alias_of": self.alias_of}
        )
        if expected != self.content_hash:
            raise ValueError("P4 artifact content_hash mismatch")
        return self


class P4GateState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    handoff_decision: str
    completeness_status: str
    blocked_families: tuple[str, ...] = ()
    degraded_families: tuple[str, ...] = ()
    execution_status: P4ExecutionStatus
    quality_status: P4QualityStatus

    @property
    def blocking(self) -> bool:
        return self.handoff_decision == "BLOCK_HANDOFF" or self.execution_status == "BLOCKED"

    @property
    def degraded(self) -> bool:
        return (
            self.execution_status == "DEGRADED"
            or self.quality_status == "DEGRADED"
            or self.handoff_decision in {"PASS_WITH_DEGRADATION", "PARTIAL_HANDOFF"}
            or self.completeness_status == "PARTIAL"
            or bool(self.blocked_families or self.degraded_families)
        )


class P4BoundaryCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    handoff: P4ArtifactEnvelope
    view_manifest: P4ArtifactEnvelope
    view_bundle: P4ArtifactEnvelope
    quality_gate: P4ArtifactEnvelope
    artifacts: dict[str, P4ArtifactEnvelope]
    gate_state: P4GateState
