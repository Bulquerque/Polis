"""Shared types, conventions, and canonical hashing for P9.S4."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, TypeAlias

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)


def _non_empty(value: str) -> str:
    if not value or not value.strip():
        raise ValueError("string must contain non-whitespace characters")
    if value != value.strip():
        raise ValueError("leading or trailing whitespace is not allowed")
    return value


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError("datetime must use UTC offset +00:00")
    return value.astimezone(UTC)


def _finite_float(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("float must be finite")
    return value


def _finite_decimal(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("decimal must be finite")
    return value


NonEmptyStr: TypeAlias = Annotated[str, AfterValidator(_non_empty)]
UtcDateTime: TypeAlias = Annotated[datetime, AfterValidator(_utc_datetime)]
FiniteFloat: TypeAlias = Annotated[float, AfterValidator(_finite_float)]
FiniteDecimal: TypeAlias = Annotated[Decimal, AfterValidator(_finite_decimal)]
Sha256: TypeAlias = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SemVer: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$"),
]


class StrictModel(BaseModel):
    """Immutable and strict boundary model."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
        validate_default=True,
    )


class MetricStatus(StrEnum):
    QUALIFIED = "QUALIFIED"
    LIMITED = "LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    UNDEFINED = "UNDEFINED"
    INVALID = "INVALID"


class GrossNet(StrEnum):
    GROSS = "GROSS"
    NET = "NET"
    ACTIVE = "ACTIVE"
    EXCESS = "EXCESS"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FrequencyMode(StrEnum):
    EXPLICIT = "EXPLICIT"
    OBSERVED_REGULAR = "OBSERVED_REGULAR"


class ReturnConvention(StrEnum):
    SIMPLE = "SIMPLE"
    LOG = "LOG"


class EvidenceClass(StrEnum):
    OBSERVED_LIVE = "OBSERVED_LIVE"
    OBSERVED_HISTORICAL = "OBSERVED_HISTORICAL"
    SIMULATED_ORDERBOOK = "SIMULATED_ORDERBOOK"
    PARAMETRIC_IMPACT = "PARAMETRIC_IMPACT"
    STRESS_EXTRAPOLATED = "STRESS_EXTRAPOLATED"
    UNAVAILABLE = "UNAVAILABLE"


class Unit(StrEnum):
    DECIMAL_RETURN = "DECIMAL_RETURN"
    ANNUALIZED_DECIMAL = "ANNUALIZED_DECIMAL"
    RATIO = "RATIO"
    PROBABILITY = "PROBABILITY"
    MONEY = "MONEY"
    BPS = "BPS"
    COUNT = "COUNT"
    SECONDS = "SECONDS"
    FRACTION = "FRACTION"
    COEFFICIENT = "COEFFICIENT"


class MetricRecord(StrictModel):
    metric_id: NonEmptyStr
    metric_version: SemVer
    producer_module_id: NonEmptyStr
    value: FiniteFloat | None
    unit: Unit
    status: MetricStatus
    gross_net: GrossNet = GrossNet.NOT_APPLICABLE
    sample_count: int = Field(ge=0)
    method: NonEmptyStr
    annualization_periods: FiniteFloat | None = Field(default=None, gt=0)
    limitations: tuple[NonEmptyStr, ...] = ()


class DiagnosticRecord(StrictModel):
    code: NonEmptyStr
    message: NonEmptyStr
    severity: Annotated[str, StringConstraints(pattern=r"^(INFO|WARNING|ERROR|BLOCKER)$")]
    observed: NonEmptyStr | None = None
    expected: NonEmptyStr | None = None


def _canonicalize(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="python", exclude_none=False))
    if isinstance(value, datetime):
        return _utc_datetime(value).isoformat().replace("+00:00", "Z")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, float):
        _finite_float(value)
        return value
    return value


def canonical_json_bytes(value: object) -> bytes:
    payload = _canonicalize(value)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def content_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sample_standard_deviation(values: list[float]) -> float:
    if len(values) < 2:
        raise ValueError("at least two observations are required")
    mean = math.fsum(values) / len(values)
    squared = math.fsum((value - mean) ** 2 for value in values)
    return math.sqrt(squared / (len(values) - 1))


def safe_mean(values: list[float]) -> float:
    if not values:
        raise ValueError("at least one observation is required")
    return math.fsum(values) / len(values)
