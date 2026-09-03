"""Canonical immutable artifact envelope for all P6 outputs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .hashing import canonical_sha256, stable_id, utc

PIPELINE_VERSION = "P6-RC6.2-P5-V2-CLOSURE-RC4"
SCHEMA_VERSION = "6.2.0-rc2"
PRODUCER_PHASE = "P6"


class FrozenModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )


class ArtifactStatus(StrEnum):
    COMPLETE = "COMPLETE"
    DEGRADED = "DEGRADED"
    EMPTY_VALID = "EMPTY_VALID"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


T = TypeVar("T", bound=BaseModel)


class ArtifactEnvelope(FrozenModel, Generic[T]):
    artifact_id: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    schema_version: str = Field(default=SCHEMA_VERSION, min_length=1)
    producer_phase: str = Field(default=PRODUCER_PHASE, min_length=1)
    producer_module_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    decision_time: datetime
    created_at: datetime
    available_at: datetime
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_count: int = Field(ge=0)
    lineage_id: str = Field(min_length=1)
    input_artifact_ids: tuple[str, ...] = ()
    status: ArtifactStatus
    records: tuple[T, ...]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("decision_time", "created_at", "available_at")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        return utc(value)

    @model_validator(mode="after")
    def validate_envelope(self) -> "ArtifactEnvelope[T]":
        if self.available_at < self.created_at:
            raise ValueError("available_at cannot precede created_at")
        if self.record_count != len(self.records):
            raise ValueError("record_count does not match records")
        if canonical_sha256(self.records) != self.content_sha256:
            raise ValueError("content_sha256 mismatch")
        if self.status is ArtifactStatus.EMPTY_VALID and self.records:
            raise ValueError("EMPTY_VALID cannot contain records")
        if self.status is ArtifactStatus.COMPLETE and not self.records:
            raise ValueError("COMPLETE artifact cannot be empty")
        return self


def build_artifact(
    *,
    artifact_type: str,
    producer_module_id: str,
    run_id: str,
    cycle_id: str,
    decision_time: datetime,
    created_at: datetime,
    available_at: datetime,
    records: Iterable[T],
    input_artifact_ids: Iterable[str] = (),
    status: ArtifactStatus | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> ArtifactEnvelope[T]:
    record_tuple = tuple(records)
    resolved_status = status or (
        ArtifactStatus.COMPLETE if record_tuple else ArtifactStatus.EMPTY_VALID
    )
    input_ids = tuple(sorted(set(input_artifact_ids)))
    content_hash = canonical_sha256(record_tuple)
    artifact_id = stable_id(
        "artifact",
        artifact_type,
        SCHEMA_VERSION,
        producer_module_id,
        content_hash,
    )
    return ArtifactEnvelope[T](
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        producer_module_id=producer_module_id,
        run_id=run_id,
        cycle_id=cycle_id,
        decision_time=decision_time,
        created_at=created_at,
        available_at=available_at,
        content_sha256=content_hash,
        record_count=len(record_tuple),
        lineage_id=stable_id(
            "lineage",
            producer_module_id,
            PIPELINE_VERSION,
            input_ids,
            content_hash,
        ),
        input_artifact_ids=input_ids,
        status=resolved_status,
        records=record_tuple,
        metadata=dict(metadata or {}),
    )
