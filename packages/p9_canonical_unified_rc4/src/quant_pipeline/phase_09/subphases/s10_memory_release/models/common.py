from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Generic, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import ModuleStatus
from quant_pipeline.phase_09.subphases.s09_competition_promotion.models import (
    ArtifactReference,
    CycleRef,
    EvidenceReference,
)

from ..hashing import sha256_hex

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ModuleId = Annotated[str, StringConstraints(pattern=r"^P9\.S10\.M0[1-4]$")]
ReasonCode = Annotated[str, StringConstraints(pattern=r"^P9_[A-Z0-9_]+$")]
MemoryItemId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=192)
]
FeedbackId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=192)]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
        str_strip_whitespace=True,
    )


class UtcTimestampedModel(StrictModel):
    @field_validator("*", mode="after")
    @classmethod
    def ensure_datetime_values_are_utc(cls, value: object) -> object:
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() != timedelta(0):
                raise ValueError("datetime values must be timezone-aware UTC")
            return value.astimezone(UTC)
        return value


class MetricValue(StrictModel):
    metric_id: NonEmptyStr
    value: float
    unit: NonEmptyStr
    metric_version: NonEmptyStr = "1.0.0"

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float) -> float:
        if not (-float("inf") < value < float("inf")):
            raise ValueError("metric values must be finite")
        return value


class ModuleDiagnostics(StrictModel):
    warnings: tuple[LongText, ...] = ()
    counters: tuple[tuple[NonEmptyStr, int], ...] = ()
    scalars: tuple[MetricValue, ...] = ()
    trace: tuple[LongText, ...] = ()


T = TypeVar("T")


class ModuleResult(StrictModel, Generic[T]):
    module_id: ModuleId
    status: ModuleStatus
    output: T | None
    diagnostics: ModuleDiagnostics
    evidence_refs: tuple[EvidenceReference, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()
    output_sha256: Sha256Hex | None = None

    @model_validator(mode="after")
    def validate_result_integrity(self) -> "ModuleResult[T]":
        if self.status == ModuleStatus.SUCCESS and self.output is None:
            raise ValueError("successful module results require an output")
        if self.output is None and self.output_sha256 is not None:
            raise ValueError("output_sha256 must be absent when output is absent")
        if self.output is not None and self.output_sha256 != sha256_hex(self.output):
            raise ValueError("output_sha256 does not match canonical output payload")
        if self.status in {ModuleStatus.INVALID, ModuleStatus.FAILED} and not self.reason_codes:
            raise ValueError("invalid or failed results require reason codes")
        return self


def build_module_result(
    *,
    module_id: ModuleId,
    status: ModuleStatus,
    output: T | None,
    diagnostics: ModuleDiagnostics | None = None,
    evidence_refs: tuple[EvidenceReference, ...] = (),
    reason_codes: tuple[ReasonCode, ...] = (),
) -> ModuleResult[T]:
    return ModuleResult[T](
        module_id=module_id,
        status=status,
        output=output,
        diagnostics=diagnostics or ModuleDiagnostics(),
        evidence_refs=evidence_refs,
        reason_codes=reason_codes,
        output_sha256=None if output is None else sha256_hex(output),
    )


def unique_artifact_refs(refs: tuple[ArtifactReference, ...]) -> tuple[ArtifactReference, ...]:
    unique: dict[tuple[str, str], ArtifactReference] = {}
    for ref in refs:
        unique[(ref.artifact_id, ref.payload_sha256)] = ref
    return tuple(sorted(unique.values(), key=lambda ref: (ref.artifact_id, ref.payload_sha256)))


__all__ = [
    "ArtifactReference",
    "CycleRef",
    "EvidenceReference",
    "FeedbackId",
    "LongText",
    "MemoryItemId",
    "MetricValue",
    "ModuleDiagnostics",
    "ModuleId",
    "ModuleResult",
    "NonEmptyStr",
    "ReasonCode",
    "Sha256Hex",
    "StrictModel",
    "UtcTimestampedModel",
    "build_module_result",
    "unique_artifact_refs",
]
