from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field

NonEmptyStr = Annotated[str, Field(min_length=1)]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class CorpusMode(StrEnum):
    LOOKUP = "LOOKUP"
    STANDARD = "STANDARD"
    TRIANGULATED = "TRIANGULATED"
    FORENSIC = "FORENSIC"


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


class CapabilityStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"


class ContentMode(StrEnum):
    RECONSTRUCTED_FROM_INDEX = "RECONSTRUCTED_FROM_INDEX"
    RAW_AUTHORIZED = "RAW_AUTHORIZED"
    METADATA_ONLY = "METADATA_ONLY"


class EvidenceDirection(StrEnum):
    SUPPORTING = "SUPPORTING"
    COUNTER = "COUNTER"
    NEUTRAL = "NEUTRAL"


class RelationCertainty(StrEnum):
    OBSERVED = "OBSERVED"
    HYPOTHESIZED = "HYPOTHESIZED"


def aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)
