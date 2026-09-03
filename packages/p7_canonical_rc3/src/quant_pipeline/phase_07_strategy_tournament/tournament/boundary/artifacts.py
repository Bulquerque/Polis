from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import Field, model_validator

from .base import TimeAwareModel
from ..domain.serialization import sha256_hex

RecordT = TypeVar("RecordT")


class ArtifactEnvelope(TimeAwareModel, Generic[RecordT]):
    _time_fields = ("decision_time", "available_at", "created_at")

    artifact_id: str
    artifact_name: str
    schema_version: str
    producer_phase: str
    producer_module_id: str
    run_id: str
    cycle_id: str
    decision_time: datetime
    available_at: datetime
    created_at: datetime
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_count: int = Field(ge=0)
    lineage_id: str
    records: tuple[RecordT, ...]

    @model_validator(mode="after")
    def validate_count(self) -> "ArtifactEnvelope[RecordT]":
        if self.record_count != len(self.records):
            raise ValueError("record_count does not match records")
        return self

    def hash_payload(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "schema_version": self.schema_version,
            "producer_phase": self.producer_phase,
            "producer_module_id": self.producer_module_id,
            "run_id": self.run_id,
            "cycle_id": self.cycle_id,
            "decision_time": self.decision_time,
            "available_at": self.available_at,
            "lineage_id": self.lineage_id,
            "records": [record.model_dump(mode="json") if hasattr(record, "model_dump") else record for record in self.records],
        }

    def calculated_hash(self) -> str:
        return sha256_hex(self.hash_payload())


def build_artifact(
    *,
    artifact_name: str,
    schema_version: str,
    producer_module_id: str,
    run_id: str,
    cycle_id: str,
    decision_time: datetime,
    execution_time: datetime,
    available_at: datetime | None = None,
    lineage_id: str,
    records: tuple[Any, ...],
) -> ArtifactEnvelope[Any]:
    knowledge_time = available_at or execution_time
    payload = {
        "artifact_name": artifact_name,
        "schema_version": schema_version,
        "producer_phase": "P7",
        "producer_module_id": producer_module_id,
        "run_id": run_id,
        "cycle_id": cycle_id,
        "decision_time": decision_time,
        "available_at": knowledge_time,
        "lineage_id": lineage_id,
        "records": [record.model_dump(mode="json") if hasattr(record, "model_dump") else record for record in records],
    }
    digest = sha256_hex(payload)
    return ArtifactEnvelope[Any](
        artifact_id=f"{artifact_name}:{digest[:24]}",
        artifact_name=artifact_name,
        schema_version=schema_version,
        producer_phase="P7",
        producer_module_id=producer_module_id,
        run_id=run_id,
        cycle_id=cycle_id,
        decision_time=decision_time,
        available_at=knowledge_time,
        created_at=execution_time,
        content_sha256=digest,
        record_count=len(records),
        lineage_id=lineage_id,
        records=records,
    )
