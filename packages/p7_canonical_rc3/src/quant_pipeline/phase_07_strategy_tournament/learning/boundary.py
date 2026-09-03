from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .domain.canonical import digest
from .domain.errors import fail


class ArtifactEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str
    artifact_name: str
    schema_version: str
    producer_phase: str
    producer_module_id: str
    pipeline_version: str
    run_id: str
    cycle_id: str
    decision_time: datetime
    available_at: datetime
    created_at: datetime
    lineage_id: str
    content_sha256: str
    record_count: int = Field(ge=0)
    records: tuple[dict[str, Any], ...]

    @field_validator("decision_time", "available_at", "created_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value

    @field_validator("records")
    @classmethod
    def records_are_mappings(cls, value: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
        return tuple(dict(record) for record in value)

    def verify(self) -> None:
        if self.record_count != len(self.records):
            fail("P7_LTR_ARTIFACT_COUNT_MISMATCH", f"{self.artifact_name} record_count mismatch")
        expected = digest(list(self.records))
        if self.content_sha256 != expected:
            fail("P7_LTR_ARTIFACT_HASH_MISMATCH", f"{self.artifact_name} content hash mismatch")


class ModuleContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    cycle_id: str
    decision_time: datetime
    available_at: datetime
    created_at: datetime
    pipeline_version: str = "P7-2.3"
    lineage_id: str


def parse_artifact(value: object, *, name: str) -> ArtifactEnvelope:
    if not isinstance(value, Mapping):
        fail("P7_LTR_CONTRACT_INVALID", f"{name} must be an artifact mapping")
    try:
        artifact = ArtifactEnvelope.model_validate(value)
    except ValidationError as exc:
        fail("P7_LTR_CONTRACT_INVALID", f"invalid {name}: {exc}")
    artifact.verify()
    if artifact.artifact_name != name:
        fail("P7_LTR_CONTRACT_INVALID", f"expected {name}, got {artifact.artifact_name}")
    return artifact


def parse_context(config: Mapping[str, object]) -> ModuleContext:
    raw = config.get("context")
    if not isinstance(raw, Mapping):
        fail("P7_LTR_CONTRACT_INVALID", "config.context is required")
    try:
        return ModuleContext.model_validate(raw)
    except ValidationError as exc:
        fail("P7_LTR_CONTRACT_INVALID", f"invalid module context: {exc}")


def build_artifact(
    *,
    name: str,
    producer_module_id: str,
    records: list[dict[str, Any]],
    context: ModuleContext,
    schema_version: str = "1.0.0",
) -> dict[str, Any]:
    content_hash = digest(records)
    artifact_id = f"{name}-{content_hash[:16]}"
    artifact = ArtifactEnvelope(
        artifact_id=artifact_id,
        artifact_name=name,
        schema_version=schema_version,
        producer_phase="phase_07_strategy_tournament",
        producer_module_id=producer_module_id,
        pipeline_version=context.pipeline_version,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        decision_time=context.decision_time,
        available_at=context.available_at,
        created_at=context.created_at,
        lineage_id=context.lineage_id,
        content_sha256=content_hash,
        record_count=len(records),
        records=tuple(records),
    )
    return artifact.model_dump(mode="json")


def module_result(
    *,
    module_id: str,
    outputs: Mapping[str, dict[str, Any]],
    metrics: Mapping[str, int | float | str | bool],
) -> dict[str, Any]:
    return {
        "module_id": module_id,
        "status": "PASS",
        "outputs": dict(outputs),
        "issues": [],
        "metrics": dict(metrics),
    }
