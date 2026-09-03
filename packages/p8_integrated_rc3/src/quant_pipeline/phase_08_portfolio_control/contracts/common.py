from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from ..foundation.models import NonEmptyStr, StrictModel, TimeAwareModel


class ArtifactReference(StrictModel):
    artifact_id: NonEmptyStr
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    contract_version: NonEmptyStr
    schema_version: NonEmptyStr


class LineageEdge(StrictModel):
    parent_artifact_id: NonEmptyStr
    parent_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    relationship_type: NonEmptyStr


class ContractEnvelope(TimeAwareModel):
    artifact_id: NonEmptyStr
    contract_version: NonEmptyStr
    schema_version: NonEmptyStr
    producer_phase: NonEmptyStr
    producer_module: NonEmptyStr
    producer_release: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    decision_time: datetime
    computed_at: datetime
    available_at: datetime
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    lineage: tuple[LineageEdge, ...]

    @field_validator("available_at")
    @classmethod
    def available_not_after_decision(cls, value: datetime, info):
        decision_time = info.data.get("decision_time")
        if decision_time is not None and value > decision_time:
            raise ValueError("available_at must not be after decision_time")
        return value
