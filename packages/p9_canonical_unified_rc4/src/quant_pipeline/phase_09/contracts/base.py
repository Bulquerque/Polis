from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, TypeAlias

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints


class StrictModel(BaseModel):
    """Immutable strict boundary model used by all public P9.S1 contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
        use_enum_values=False,
    )


NonEmptyStr: TypeAlias = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
Sha256Hex: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{64}$"),
]
SemanticVersion: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$"),
]
ModuleId: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^P[0-9]+\.S[0-9]+\.M[0-9]+$"),
]
PhaseId: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^P[0-9]+$"),
]
ArtifactId: TypeAlias = NonEmptyStr
RecordId: TypeAlias = NonEmptyStr
RunId: TypeAlias = NonEmptyStr
CycleId: TypeAlias = NonEmptyStr
BacktestId: TypeAlias = NonEmptyStr
ReasonCode: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^P9_[A-Z0-9_]+$"),
]


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError("datetime must use UTC offset +00:00")
    return value.astimezone(UTC)


UtcDateTime: TypeAlias = Annotated[datetime, AfterValidator(ensure_utc)]


def finite_decimal(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("decimal must be finite")
    return value


FiniteDecimal: TypeAlias = Annotated[Decimal, AfterValidator(finite_decimal)]


class Availability(StrEnum):
    AVAILABLE = "AVAILABLE"
    LIMITED = "LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    RESERVED = "RESERVED"


class ModuleStatus(StrEnum):
    SUCCESS = "SUCCESS"
    LIMITED = "LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INVALID = "INVALID"
    FAILED = "FAILED"
    SKIPPED_UPSTREAM_BLOCKED = "SKIPPED_UPSTREAM_BLOCKED"


class EvidenceClass(StrEnum):
    FACTUAL_EXECUTED = "FACTUAL_EXECUTED"
    FACTUAL_OBSERVED_NOT_EXECUTED = "FACTUAL_OBSERVED_NOT_EXECUTED"
    OBSERVABLE_COUNTERFACTUAL = "OBSERVABLE_COUNTERFACTUAL"
    MODEL_BASED_COUNTERFACTUAL = "MODEL_BASED_COUNTERFACTUAL"
    CENSORED = "CENSORED"
    UNAVAILABLE = "UNAVAILABLE"
