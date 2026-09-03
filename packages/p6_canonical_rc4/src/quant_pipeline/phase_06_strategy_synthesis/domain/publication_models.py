"""Canonical publication, lineage, and P7 V2 handoff models."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from ..foundation.artifacts import FrozenModel
from ..foundation.hashing import utc
from .enums import TemplateId
from .strategy_models import StrategyLeg

class StrategyLegRecord(FrozenModel):
    candidate_id: str
    leg: StrategyLeg


class StrategyLineageRecord(FrozenModel):
    candidate_id: str
    lineage_id: str
    source_artifact_ids: tuple[str, ...]
    generation_run_id: str
    origin_template_id: TemplateId


class ArtifactReference(FrozenModel):
    artifact_type: str
    artifact_id: str
    content_sha256: str
    record_count: int
    schema_version: str


class Phase7StrategyHandoffManifest(FrozenModel):
    handoff_id: str
    target_phase: str = "P7"
    decision_time: datetime
    cycle_id: str
    candidate_count: int = Field(ge=0)
    snapshot_hash: str
    generation_policy_version: str
    artifact_references: tuple[ArtifactReference, ...]
    candidate_ids_sha256: str
    production_promotion_allowed: bool = False

    @field_validator("decision_time")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc(value)


