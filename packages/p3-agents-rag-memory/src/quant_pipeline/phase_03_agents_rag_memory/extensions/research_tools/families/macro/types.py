from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field

NonEmptyStr = Annotated[str, Field(min_length=1)]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class MacroMode(StrEnum):
    LOOKUP = "LOOKUP"
    CONTEXT = "CONTEXT"
    VINTAGE_ANALYSIS = "VINTAGE_ANALYSIS"


class VintagePolicy(StrEnum):
    KNOWN_AT_DECISION_TIME = "KNOWN_AT_DECISION_TIME"
    ORIGINAL_RELEASE = "ORIGINAL_RELEASE"
    LATEST_KNOWN_AT_DECISION_TIME = "LATEST_KNOWN_AT_DECISION_TIME"


class Transformation(StrEnum):
    LEVEL = "LEVEL"
    DIFFERENCE = "DIFFERENCE"
    PERCENT_CHANGE = "PERCENT_CHANGE"
    LOG_DIFFERENCE = "LOG_DIFFERENCE"
    YEAR_OVER_YEAR = "YEAR_OVER_YEAR"
    ANNUALIZED = "ANNUALIZED"


class ComparisonKind(StrEnum):
    RAW_ALIGNED = "RAW_ALIGNED"
    DIFFERENCE_FROM_FIRST = "DIFFERENCE_FROM_FIRST"
    RATIO_TO_FIRST = "RATIO_TO_FIRST"
    SPREAD_TO_FIRST = "SPREAD_TO_FIRST"
    INDEX_BASE_100 = "INDEX_BASE_100"


class AlignmentPolicy(StrEnum):
    INNER = "INNER"
    OUTER = "OUTER"


class Frequency(StrEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUAL = "ANNUAL"
    IRREGULAR = "IRREGULAR"
    UNKNOWN = "UNKNOWN"


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


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def parse_date(value: object, *, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    token = str(value).strip()
    if not token:
        raise ValueError(f"{field} is required")
    try:
        return date.fromisoformat(token[:10])
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO date") from exc


def parse_datetime(value: object, *, field: str) -> datetime:
    if isinstance(value, datetime):
        return aware_utc(value)
    token = str(value).strip()
    if not token:
        raise ValueError(f"{field} is required")
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(token)
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO datetime") from exc
    return aware_utc(parsed)
