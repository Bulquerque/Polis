from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from quant_pipeline.common.hashing.hash_utils import canonical_sha256

ExecutionStatus = Literal[
    "PRODUCED",
    "DEGRADED",
    "BLOCKED",
    "SKIPPED_NOT_AVAILABLE",
    "SKIPPED_NOT_AUTHORIZED",
    "UNAVAILABLE_UPSTREAM",
    "FAILED_NONBLOCKING",
    "NOT_RUN",
]
QualityStatus = Literal["VALIDATED", "PASS", "DEGRADED", "BLOCKED", "NOT_EVALUATED"]


class RuntimeExecutionContext(BaseModel):
    """Minimal immutable context shared by the S7-S9 artifact runtime."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    cycle_id: str
    as_of_time: AwareDatetime
    created_at: AwareDatetime
    pipeline_version: str


class ArtifactEnvelope(BaseModel):
    """Canonical P4 artifact envelope used by the integrated downstream pipeline."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str
    artifact_name: str
    schema_version: str
    producer_phase: str
    producer_module_id: str
    run_id: str
    cycle_id: str
    as_of_time: AwareDatetime
    created_at: AwareDatetime
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_count: int = Field(ge=0)
    grain: tuple[str, ...]
    lineage_id: str
    execution_status: ExecutionStatus
    quality_status: QualityStatus
    records: tuple[dict[str, Any], ...]
    metadata: dict[str, Any] = Field(default_factory=dict)
    alias_of: str | None = None

    def verify_integrity(self) -> None:
        if self.record_count != len(self.records):
            raise ValueError("record_count does not match records")
        expected = canonical_sha256(
            {"records": self.records, "metadata": self.metadata, "alias_of": self.alias_of}
        )
        if expected != self.content_hash:
            raise ValueError("content_hash does not match canonical payload")

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        self.verify_integrity()
        return self


def build_artifact(
    *,
    artifact_name: str,
    schema_version: str,
    producer_module_id: str,
    context: RuntimeExecutionContext,
    grain: tuple[str, ...],
    records: list[dict[str, Any]],
    lineage_id: str,
    metadata: dict[str, Any] | None = None,
    alias_of: str | None = None,
    execution_status: ExecutionStatus = "PRODUCED",
    quality_status: QualityStatus = "VALIDATED",
) -> ArtifactEnvelope:
    safe_records = deepcopy(records)
    safe_metadata = deepcopy(metadata or {})
    payload_hash = canonical_sha256(
        {"records": safe_records, "metadata": safe_metadata, "alias_of": alias_of}
    )
    return ArtifactEnvelope(
        artifact_id=f"{artifact_name}:{payload_hash[:16]}",
        artifact_name=artifact_name,
        schema_version=schema_version,
        producer_phase="phase_04_feature_base",
        producer_module_id=producer_module_id,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        as_of_time=context.as_of_time,
        created_at=context.created_at,
        content_hash=payload_hash,
        record_count=len(safe_records),
        grain=grain,
        lineage_id=lineage_id,
        execution_status=execution_status,
        quality_status=quality_status,
        records=tuple(safe_records),
        metadata=safe_metadata,
        alias_of=alias_of,
    )
