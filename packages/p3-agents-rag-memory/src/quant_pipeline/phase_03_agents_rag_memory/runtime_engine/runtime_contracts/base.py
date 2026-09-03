from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NonEmptyStr = Annotated[str, Field(min_length=1)]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_default=True,
        str_strip_whitespace=True,
    )


class ArtifactStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    EMPTY_VALID = "EMPTY_VALID"
    SKIPPED_NOT_APPLICABLE = "SKIPPED_NOT_APPLICABLE"


class ExecutionMode(StrEnum):
    LIVE = "LIVE"
    WARMUP_REPLAY = "WARMUP_REPLAY"
    REPLAY = "REPLAY"
    DRY_RUN = "DRY_RUN"


class BeliefDirection(StrEnum):
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    POSITIVE = "POSITIVE"


class SocialLifecycle(StrEnum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    DELIVERED = "DELIVERED"
    SEEN = "SEEN"
    INTERPRETED = "INTERPRETED"
    USED = "USED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class LineageRecord(StrictModel):
    lineage_id: NonEmptyStr
    producer_module_id: NonEmptyStr
    source_artifact_ids: tuple[NonEmptyStr, ...] = ()
    source_hashes: dict[str, str] = Field(default_factory=dict)


class CanonicalArtifact(StrictModel):
    schema_id: NonEmptyStr
    schema_version: NonEmptyStr = "1.0.0"
    artifact_id: NonEmptyStr
    pipeline_version: NonEmptyStr = "V14.1-RC4.1"
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    as_of_time: datetime
    created_at: datetime
    status: ArtifactStatus = ArtifactStatus.READY
    reason_codes: tuple[str, ...] = ()
    lineage: LineageRecord

    @field_validator("as_of_time", "created_at")
    @classmethod
    def aware_datetime(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def empty_state_is_explicit(self) -> "CanonicalArtifact":
        records = getattr(self, "records", None)
        if self.created_at < self.as_of_time:
            raise ValueError("created_at cannot precede as_of_time")
        if records == () and self.status is ArtifactStatus.READY:
            raise ValueError("empty artifacts must use EMPTY_VALID, DEGRADED, or FAILED")
        return self
