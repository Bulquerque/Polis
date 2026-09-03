"""Artifact envelopes, manifests and receipts."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


AwareDateTime = Annotated[datetime, Field(description="Timezone-aware UTC-compatible datetime")]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


class ArtifactEnvelope(FrozenModel):
    artifact_id: str
    artifact_name: str
    schema_version: str
    producer_phase: str
    producer_module_id: str
    run_id: str
    cycle_id: str
    decision_time: AwareDateTime
    available_at: AwareDateTime
    created_at: AwareDateTime
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_count: int = Field(ge=0)
    lineage_id: str
    records: tuple[dict[str, object], ...]

    _decision_aware = field_validator("decision_time")(_aware)
    _available_aware = field_validator("available_at")(_aware)
    _created_aware = field_validator("created_at")(_aware)

    @model_validator(mode="after")
    def validate_envelope(self) -> "ArtifactEnvelope":
        if self.record_count != len(self.records):
            raise ValueError("record_count does not match records")
        if self.available_at > self.decision_time:
            raise ValueError("artifact available_at is after decision_time")
        return self


class ArtifactReference(FrozenModel):
    artifact_name: str
    artifact_id: str
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: str
    record_count: int = Field(ge=0)


class HandoffManifestRecord(FrozenModel):
    contract_id: str
    contract_version: str
    producer: str
    consumer: str
    artifact_references: tuple[ArtifactReference, ...]
    policy_versions: dict[str, str] = Field(default_factory=dict)
    candidate_count: int = Field(ge=0)
    forbidden_fields_scanned: bool
    candidate_conservation_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ModuleReceipt(FrozenModel):
    module_id: str
    trace_id: str
    run_id: str
    cycle_id: str
    status: str
    input_artifact_ids: tuple[str, ...]
    output_artifact_ids: tuple[str, ...]
    counts: dict[str, int]
    reason_code_distribution: dict[str, int]
    policy_versions: dict[str, str]
    duration_ms: float = Field(ge=0)
