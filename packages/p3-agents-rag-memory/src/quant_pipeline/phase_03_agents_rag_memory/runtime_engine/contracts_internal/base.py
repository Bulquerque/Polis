from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum, StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

NonEmptyStr = Annotated[str, Field(min_length=1)]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
JsonObject = dict[str, JsonValue]


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def _json_default(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return utc(value).isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_json_default,
    )


def content_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class StrictBoundaryModel(BaseModel):
    """Immutable, strict public-boundary model for the A/B integration contract pack."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_default=True,
        str_strip_whitespace=True,
    )


class ExecutionMode(StrEnum):
    WARMUP_REPLAY = "WARMUP_REPLAY"
    LIVE = "LIVE"
    REPLAY = "REPLAY"
    DRY_RUN = "DRY_RUN"


class ExecutionStatus(StrEnum):
    READY = "READY"
    EMPTY_VALID = "EMPTY_VALID"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    SKIPPED_NOT_APPLICABLE = "SKIPPED_NOT_APPLICABLE"


class RuntimeIssue(StrictBoundaryModel):
    code: NonEmptyStr
    message: NonEmptyStr
    severity: Annotated[str, Field(pattern=r"^(INFO|WARNING|ERROR)$")]
    module_id: NonEmptyStr | None = None
    artifact_id: NonEmptyStr | None = None


class TemporalEnvelope(StrictBoundaryModel):
    as_of_time: datetime
    created_at: datetime

    @field_validator("as_of_time", "created_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return utc(value)

    @model_validator(mode="after")
    def created_not_before_cutoff(self) -> "TemporalEnvelope":
        if self.created_at < self.as_of_time:
            raise ValueError("created_at cannot precede as_of_time")
        return self


class LineageRecord(StrictBoundaryModel):
    lineage_id: NonEmptyStr
    producer_module_id: Annotated[str, Field(pattern=r"^(?:P3\.S(?:[1-9]|[12][0-9]|3[0-1])\.M\d{2}|P3\.ORCHESTRATOR)$")]
    source_artifact_ids: tuple[NonEmptyStr, ...] = ()
    source_hashes: tuple[Sha256, ...] = ()

    @model_validator(mode="after")
    def aligned_sources(self) -> "LineageRecord":
        if len(self.source_artifact_ids) != len(self.source_hashes):
            raise ValueError("lineage source_artifact_ids and source_hashes must have equal length")
        if len(set(self.source_artifact_ids)) != len(self.source_artifact_ids):
            raise ValueError("lineage source_artifact_ids must be unique")
        return self


class ArtifactPointer(StrictBoundaryModel):
    artifact_name: NonEmptyStr
    schema_id: NonEmptyStr
    schema_version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    artifact_id: NonEmptyStr
    content_hash: Sha256
    storage_ref: NonEmptyStr
    producer_module_id: Annotated[str, Field(pattern=r"^(?:P3\.S(?:[1-9]|[12][0-9]|3[0-1])\.M\d{2}|P3\.ORCHESTRATOR)$")]
    status: ExecutionStatus
    row_count: NonNegativeInt | None = None
    grain: tuple[NonEmptyStr, ...] = ()
    lineage_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def status_metadata_consistent(self) -> "ArtifactPointer":
        if self.status is ExecutionStatus.EMPTY_VALID and self.row_count not in {None, 0}:
            raise ValueError("EMPTY_VALID artifact cannot have a positive row_count")
        if len(set(self.grain)) != len(self.grain):
            raise ValueError("artifact grain fields must be unique")
        return self


class ResolvedArtifact(StrictBoundaryModel):
    pointer: ArtifactPointer
    payload: JsonObject

    @model_validator(mode="after")
    def hash_matches_payload(self) -> "ResolvedArtifact":
        if content_hash(self.payload) != self.pointer.content_hash:
            raise ValueError("resolved artifact content hash does not match pointer")
        return self
