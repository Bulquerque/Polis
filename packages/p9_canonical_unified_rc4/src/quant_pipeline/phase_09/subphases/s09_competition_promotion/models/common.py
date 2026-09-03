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

from ..enums import EvidenceQuality, GateSeverity, GateState, ModuleStatus
from ..hashing import sha256_hex

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ModuleId = Annotated[str, StringConstraints(pattern=r"^P9\.S9\.M0[1-7]$")]
ConfigId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
ArtifactId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
PolicyId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
ReasonCode = Annotated[str, StringConstraints(pattern=r"^P9_[A-Z0-9_]+$")]


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


class CycleRef(StrictModel):
    cycle_id: NonEmptyStr
    ordinal: int = Field(ge=0)


class ArtifactReference(UtcTimestampedModel):
    artifact_id: ArtifactId
    artifact_role: NonEmptyStr
    schema_name: NonEmptyStr
    schema_version: NonEmptyStr
    schema_sha256: Sha256Hex
    payload_sha256: Sha256Hex
    producer_module_id: NonEmptyStr
    run_id: NonEmptyStr
    cycle: CycleRef
    available_at: datetime
    location: NonEmptyStr


class EvidenceReference(StrictModel):
    evidence_id: NonEmptyStr
    artifact_ref: ArtifactReference
    quality: EvidenceQuality
    summary: LongText


class GateEvidence(StrictModel):
    gate_id: NonEmptyStr
    state: GateState
    severity: GateSeverity
    evidence_refs: tuple[EvidenceReference, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()
    limitations: tuple[LongText, ...] = ()

    @model_validator(mode="after")
    def validate_gate_semantics(self) -> "GateEvidence":
        if self.state == GateState.FAIL and not self.reason_codes:
            raise ValueError("failed gates require at least one reason code")
        is_blocking = self.severity in {GateSeverity.BLOCKING, GateSeverity.CRITICAL}
        if is_blocking and self.state == GateState.PASS:
            return self
        return self


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
        if self.output is not None:
            expected = sha256_hex(self.output)
            if self.output_sha256 != expected:
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
