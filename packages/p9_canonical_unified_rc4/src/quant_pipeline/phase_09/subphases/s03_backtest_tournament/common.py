"""Shared immutable types and canonical hashing for P9.S3."""

from __future__ import annotations

import hashlib
import json
import math
import re
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
    model_validator,
)


_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
_MODULE_RE = re.compile(
    r"^(?:P[0-9]+(?:\.S[0-9]+)?(?:\.M[0-9]+)?|"
    r"PHASE_[0-9]{2}|EXTERNAL\.[A-Z0-9_.-]+)$"
)


def _non_empty(value: str) -> str:
    if not value or not value.strip():
        raise ValueError("string must contain non-whitespace characters")
    if value != value.strip():
        raise ValueError("leading or trailing whitespace is not allowed")
    return value


def _semver(value: str) -> str:
    _non_empty(value)
    if _SEMVER_RE.fullmatch(value) is None:
        raise ValueError("value must be semantic version text")
    return value


def _module_id(value: str) -> str:
    _non_empty(value)
    if _MODULE_RE.fullmatch(value) is None:
        raise ValueError("invalid producer/module identifier")
    return value


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError("datetime must use UTC offset +00:00")
    return value.astimezone(UTC)


def _finite_decimal(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("decimal must be finite")
    return value


def _finite_float(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("float must be finite")
    return value


NonEmptyStr: TypeAlias = Annotated[str, AfterValidator(_non_empty)]
SemVer: TypeAlias = Annotated[str, AfterValidator(_semver)]
ModuleId: TypeAlias = Annotated[str, AfterValidator(_module_id)]
UtcDateTime: TypeAlias = Annotated[datetime, AfterValidator(_utc_datetime)]
Sha256: TypeAlias = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
FiniteDecimal: TypeAlias = Annotated[Decimal, AfterValidator(_finite_decimal)]
FiniteFloat: TypeAlias = Annotated[float, AfterValidator(_finite_float)]


class StrictModel(BaseModel):
    """Project-wide boundary defaults for immutable, strict contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
        validate_default=True,
    )


class Availability(StrEnum):
    AVAILABLE = "AVAILABLE"
    LIMITED = "LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    LEGACY_RESEARCH_ONLY = "LEGACY_RESEARCH_ONLY"


class TerminalStatus(StrEnum):
    SUCCESS = "SUCCESS"
    NO_ACTION_VALID = "NO_ACTION_VALID"
    LIMITED = "LIMITED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INVALID = "INVALID"
    FAILED = "FAILED"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    CANCELLED_UPSTREAM = "CANCELLED_UPSTREAM"


class ArtifactReference(StrictModel):
    artifact_id: NonEmptyStr
    artifact_type: NonEmptyStr
    artifact_schema_name: NonEmptyStr
    artifact_schema_version: SemVer
    content_sha256: Sha256
    producer_module_id: ModuleId
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    available_at: UtcDateTime
    location: NonEmptyStr
    availability: Availability = Availability.AVAILABLE
    record_count: int | None = Field(default=None, ge=0)


class DiagnosticRecord(StrictModel):
    code: NonEmptyStr
    message: NonEmptyStr
    severity: Annotated[str, StringConstraints(pattern=r"^(INFO|WARNING|ERROR|BLOCKER)$")]
    observed: NonEmptyStr | None = None
    expected: NonEmptyStr | None = None


class EvidenceRecord(StrictModel):
    evidence_id: NonEmptyStr
    evidence_type: NonEmptyStr
    producer_module_id: ModuleId
    content_sha256: Sha256
    artifact_refs: tuple[ArtifactReference, ...] = ()
    diagnostics: tuple[DiagnosticRecord, ...] = ()


class ModuleReceipt(StrictModel):
    module_id: ModuleId
    status: TerminalStatus
    started_at: UtcDateTime
    completed_at: UtcDateTime
    input_refs: tuple[ArtifactReference, ...] = ()
    output_refs: tuple[ArtifactReference, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_receipt(self):
        if self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        if self.status is TerminalStatus.SUCCESS and not self.output_refs:
            raise ValueError("SUCCESS receipt requires output_refs")
        if self.status in {TerminalStatus.FAILED, TerminalStatus.INVALID} and not self.reason_codes:
            raise ValueError("failed or invalid receipt requires reason_codes")
        return self


    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()


class DurationSpec(StrictModel):
    seconds: int = Field(ge=0)

    def as_timedelta(self) -> timedelta:
        return timedelta(seconds=self.seconds)


class TimeWindow(StrictModel):
    start: UtcDateTime
    end: UtcDateTime

    @model_validator(mode="after")
    def validate_order(self):
        if self.end <= self.start:
            raise ValueError("time window must have positive duration")
        return self

    def duration(self) -> timedelta:
        return self.end - self.start

    def contains(self, value: datetime) -> bool:
        return self.start <= value < self.end


class HashProtocol(StrEnum):
    JSON_CANONICAL_V1 = "JSON_CANONICAL_V1"


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
            for key, item in sorted(value.items(), key=lambda x: str(x[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, float):
        _finite_float(value)
        return value
    return value


def canonical_json_bytes(value: object) -> bytes:
    payload = _canonicalize(value)
    text = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return text.encode("utf-8")


def content_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def stable_seed(*parts: str, modulo: int = 2**32 - 1) -> int:
    if modulo <= 0:
        raise ValueError("modulo must be positive")
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % modulo
