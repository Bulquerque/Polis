"""Shared strict types for P3.S28."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
SignedBelief = Annotated[float, Field(ge=-1.0, le=1.0)]
BeliefDelta = Annotated[float, Field(ge=-2.0, le=2.0)]
PositiveFloat = Annotated[float, Field(gt=0.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]
PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]


def as_tuple(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    raise TypeError("expected a JSON array")


def as_datetime(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise TypeError("expected ISO-8601 datetime")
    if value.tzinfo is None:
        raise ValueError("datetime must include timezone")
    return value.astimezone(UTC)


AwareDateTime = Annotated[datetime, BeforeValidator(as_datetime), AfterValidator(lambda x: x.astimezone(UTC))]
StringTuple = Annotated[tuple[NonEmptyStr, ...], BeforeValidator(as_tuple)]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, validate_default=True, use_enum_values=False)


class MetricStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    NO_COVERAGE = "NO_COVERAGE"
    BLOCKED = "BLOCKED"
    MISSING = "MISSING"


class ProjectionStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    SUPPRESSED_SMALL_COHORT = "SUPPRESSED_SMALL_COHORT"
    NO_COVERAGE = "NO_COVERAGE"


class QualityStatus(StrEnum):
    PASS = "PASS"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    NO_COVERAGE = "NO_COVERAGE"


class IssueSeverity(StrEnum):
    WARNING = "WARNING"
    ERROR = "ERROR"


class SourceQualityStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


def enum_parser(enum_type: type[StrEnum]):
    def parse(value: Any) -> StrEnum:
        if isinstance(value, enum_type):
            return value
        if isinstance(value, str):
            return enum_type(value)
        raise TypeError(f"expected {enum_type.__name__}")
    return parse


MetricStatusValue = Annotated[MetricStatus, BeforeValidator(enum_parser(MetricStatus))]
ProjectionStatusValue = Annotated[ProjectionStatus, BeforeValidator(enum_parser(ProjectionStatus))]
QualityStatusValue = Annotated[QualityStatus, BeforeValidator(enum_parser(QualityStatus))]
IssueSeverityValue = Annotated[IssueSeverity, BeforeValidator(enum_parser(IssueSeverity))]
SourceQualityStatusValue = Annotated[SourceQualityStatus, BeforeValidator(enum_parser(SourceQualityStatus))]


class ArtifactContext(StrictModel):
    schema_version: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonNegativeInt
    as_of_time: AwareDateTime
    lineage_id: NonEmptyStr


class MetricGrain(StrictModel):
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    as_of_time: AwareDateTime

    def key(self) -> tuple[str, str, str, datetime]:
        return (self.underlying_id, self.proposition_id, self.horizon, self.as_of_time)
