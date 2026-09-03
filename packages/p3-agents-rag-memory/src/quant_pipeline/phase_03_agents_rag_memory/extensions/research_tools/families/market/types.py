from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field

NonEmptyStr = Annotated[str, Field(min_length=1)]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]
PositiveInt = Annotated[int, Field(gt=0)]


class MarketMode(StrEnum):
    OBSERVE = "OBSERVE"
    DIAGNOSTIC = "DIAGNOSTIC"
    STRUCTURAL = "STRUCTURAL"


class OptionMode(StrEnum):
    CONTRACT_LOOKUP = "CONTRACT_LOOKUP"
    CHAIN_DIAGNOSTIC = "CHAIN_DIAGNOSTIC"
    STRUCTURE_HISTORY = "STRUCTURE_HISTORY"
    SURFACE_ANALYSIS = "SURFACE_ANALYSIS"


class OutcomeStatus(StrEnum):
    PASS = "PASS"
    EMPTY_VALID = "EMPTY_VALID"
    DEGRADED = "DEGRADED"
    BLOCKED_UPSTREAM = "BLOCKED_UPSTREAM"


class QualificationStatus(StrEnum):
    QUALIFIED_LOCAL = "QUALIFIED_LOCAL"
    DEGRADED = "DEGRADED"
    BLOCKED_UPSTREAM = "BLOCKED_UPSTREAM"
    FAILED = "FAILED"


class ViewReadinessStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED_UPSTREAM = "BLOCKED_UPSTREAM"
    FAILED = "FAILED"


class AdjustmentPolicy(StrEnum):
    RAW = "RAW"
    PIT_SPLIT_ADJUSTED = "PIT_SPLIT_ADJUSTED"
    PIT_TOTAL_RETURN = "PIT_TOTAL_RETURN"


class NormalizationPolicy(StrEnum):
    NONE = "NONE"
    BASE_100 = "BASE_100"
    CUMULATIVE_RETURN = "CUMULATIVE_RETURN"


class OptionType(StrEnum):
    CALL = "CALL"
    PUT = "PUT"
    UNKNOWN = "UNKNOWN"


class SurfaceDiagnosticStatus(StrEnum):
    OBSERVED_IV = "OBSERVED_IV"
    QUOTE_ONLY = "QUOTE_ONLY"
    INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"


def aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)
