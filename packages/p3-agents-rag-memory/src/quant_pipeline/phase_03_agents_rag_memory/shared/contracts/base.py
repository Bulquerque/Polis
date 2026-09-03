from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HEX64 = r"^[a-f0-9]{64}$"


class StrictModel(BaseModel):
    """Immutable strict model used at package and integration boundaries."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_default=True,
        populate_by_name=True,
    )


class ReadinessStatus(StrEnum):
    READY = "READY"
    EMPTY_VALID = "EMPTY_VALID"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    SKIPPED_NOT_APPLICABLE = "SKIPPED_NOT_APPLICABLE"


class StorageScheme(StrEnum):
    FILE = "file"
    OBJECT_STORE = "object_store"
    DATABASE = "database"
    MEMORY = "memory"
    TEST_FIXTURE = "test_fixture"


class StorageReference(StrictModel):
    """Opaque artifact location resolved only through an ArtifactResolverPort."""

    scheme: StorageScheme
    location: str = Field(min_length=1)
    version: str | None = None


class TemporalEnvelope(StrictModel):
    """Canonical temporal semantics shared by foundation and runtime."""

    as_of_time: datetime
    event_time: datetime | None = None
    effective_time: datetime | None = None
    available_at: datetime | None = None
    ingested_at: datetime | None = None
    processed_at: datetime | None = None

    @field_validator(
        "as_of_time",
        "event_time",
        "effective_time",
        "available_at",
        "ingested_at",
        "processed_at",
    )
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("all timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def enforce_point_in_time(self) -> "TemporalEnvelope":
        if self.available_at is not None and self.available_at > self.as_of_time:
            raise ValueError("available_at must not exceed as_of_time")
        return self


class LineageRecord(StrictModel):
    lineage_id: str = Field(min_length=1)
    source_artifact_ids: tuple[str, ...] = ()
    parent_lineage_ids: tuple[str, ...] = ()
    transformation_ids: tuple[str, ...] = ()


def model_or_mapping(value: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    return dict(value)


def canonical_json(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def content_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class ArtifactPointer(StrictModel):
    """Hash-bound reference to an immutable artifact.

    The pointer contains no payload and never exposes a provider SDK. Consumers
    resolve ``storage_ref`` through an injected ``ArtifactResolverPort``.
    """

    artifact_name: str = Field(min_length=1)
    schema_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    content_hash: str = Field(pattern=HEX64)
    status: ReadinessStatus
    storage_ref: StorageReference
    media_type: str = Field(default="application/json", min_length=1)
    producer_module_id: str | None = None
    lineage_id: str | None = None
    row_count: int | None = Field(default=None, ge=0)
    grain: tuple[str, ...] = ()
    available_at: datetime | None = None

    @field_validator("available_at")
    @classmethod
    def available_at_timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("available_at must be timezone-aware")
        return value.astimezone(UTC)


class RunIdentity(StrictModel):
    run_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    as_of_time: datetime
    pipeline_version: str = Field(min_length=1)
    architecture_revision: str = Field(min_length=1)

    @field_validator("as_of_time")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of_time must be timezone-aware")
        return value.astimezone(UTC)

    @property
    def as_of(self) -> datetime:
        """Compatibility alias for code written before Contract Pack v1."""

        return self.as_of_time
