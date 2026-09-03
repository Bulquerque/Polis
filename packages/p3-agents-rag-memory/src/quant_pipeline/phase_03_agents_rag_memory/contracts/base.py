from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from enum import Enum, StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NonEmptyStr = Annotated[str, Field(min_length=1)]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SemVer = Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]

CONTRACT_PACK_ID = "P3_INTEGRATION_CONTRACT_PACK_V2"
CONTRACT_PACK_VERSION = "2.0.0"


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def _json_default(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return utc(value).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
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


class ContractModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_default=True,
        str_strip_whitespace=True,
    )


class ArtifactStatus(StrEnum):
    READY = "READY"
    EMPTY_VALID = "EMPTY_VALID"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    SKIPPED_NOT_APPLICABLE = "SKIPPED_NOT_APPLICABLE"


class CycleStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    DRY_RUN_VALIDATED = "DRY_RUN_VALIDATED"


class ExecutionMode(StrEnum):
    WARMUP_REPLAY = "WARMUP_REPLAY"
    LIVE = "LIVE"
    REPLAY = "REPLAY"
    DRY_RUN = "DRY_RUN"


class StateSource(StrEnum):
    GENESIS = "GENESIS"
    WARMUP_CHECKPOINT = "WARMUP_CHECKPOINT"
    PRIOR_CYCLE = "PRIOR_CYCLE"


class StorageReference(ContractModel):
    scheme: Annotated[str, Field(pattern=r"^(file|object_store|database|memory|test_fixture)$")]
    location: NonEmptyStr
    version: str | None = None


class RunIdentity(ContractModel):
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    as_of_time: datetime
    pipeline_version: NonEmptyStr
    architecture_revision: NonEmptyStr

    @field_validator("as_of_time")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return utc(value)


class LineageSource(ContractModel):
    artifact_id: NonEmptyStr
    content_hash: Sha256


class LineageRecord(ContractModel):
    lineage_id: NonEmptyStr
    producer_module_id: Annotated[
        str,
        Field(pattern=r"^(?:P3\.S(?:[1-9]|[12][0-9]|3[0-1])\.M\d{2}|P3\.ORCHESTRATOR)$"),
    ]
    sources: tuple[LineageSource, ...] = ()
    parent_lineage_ids: tuple[NonEmptyStr, ...] = ()
    transformation_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def unique_sources(self) -> "LineageRecord":
        ids = [source.artifact_id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("lineage sources must be unique")
        return self


class ArtifactPointer(ContractModel):
    artifact_name: NonEmptyStr
    schema_id: NonEmptyStr
    schema_version: SemVer
    artifact_id: NonEmptyStr
    content_hash: Sha256
    status: ArtifactStatus
    storage_ref: StorageReference
    media_type: NonEmptyStr = "application/json"
    producer_module_id: Annotated[
        str,
        Field(pattern=r"^(?:P3\.S(?:[1-9]|[12][0-9]|3[0-1])\.M\d{2}|P3\.ORCHESTRATOR)$"),
    ]
    lineage_id: str | None = None
    row_count: int | None = Field(default=None, ge=0)
    grain: tuple[NonEmptyStr, ...] = ()
    available_at: datetime | None = None

    @field_validator("available_at")
    @classmethod
    def aware_available_at(cls, value: datetime | None) -> datetime | None:
        return None if value is None else utc(value)

    @model_validator(mode="after")
    def metadata_consistent(self) -> "ArtifactPointer":
        if self.status is ArtifactStatus.EMPTY_VALID and self.row_count not in {None, 0}:
            raise ValueError("EMPTY_VALID artifact cannot have a positive row_count")
        if len(set(self.grain)) != len(self.grain):
            raise ValueError("grain fields must be unique")
        return self
