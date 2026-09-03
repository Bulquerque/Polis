"""Shared, strongly typed contracts for canonical P5 V2 artifacts."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from .core import FrozenModel


class CapabilityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    LIMITED = "LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    SKIPPED_CAPABILITY_UNAVAILABLE = "SKIPPED_CAPABILITY_UNAVAILABLE"


class CalibrationStatus(StrEnum):
    CALIBRATED = "CALIBRATED"
    PARTIALLY_CALIBRATED = "PARTIALLY_CALIBRATED"
    UNCALIBRATED = "UNCALIBRATED"
    UNAVAILABLE = "UNAVAILABLE"


class ValidityStatus(StrEnum):
    VALID = "VALID"
    DEGRADED = "DEGRADED"
    LIMITED = "LIMITED"
    REJECTED = "REJECTED"
    UNAVAILABLE = "UNAVAILABLE"


class ScenarioType(StrEnum):
    NOMINAL = "NOMINAL"
    ADVERSARIAL = "ADVERSARIAL"
    STRESS = "STRESS"


class V2ArtifactIdentity(FrozenModel):
    artifact_id: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: str = Field(default="2.0.0", min_length=1)
    producer_phase: str = Field(default="P5", pattern=r"^P5$")
    producer_module_id: str = Field(pattern=r"^P5\.S[1-9]\.M\d{2}$")
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    decision_time: datetime
    created_at: datetime
    available_at: datetime
    lineage_id: str = Field(min_length=1)

    @field_validator("decision_time", "created_at", "available_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("artifact clocks must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_clocks(self) -> "V2ArtifactIdentity":
        if self.created_at > self.decision_time:
            raise ValueError("created_at cannot exceed decision_time")
        if self.available_at < self.created_at:
            raise ValueError("available_at cannot precede created_at")
        if self.available_at > self.decision_time:
            raise ValueError("available_at cannot exceed decision_time")
        return self
