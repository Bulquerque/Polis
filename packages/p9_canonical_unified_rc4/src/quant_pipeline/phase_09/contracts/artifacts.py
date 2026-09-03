from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from .base import (
    ArtifactId,
    Availability,
    BacktestId,
    CycleId,
    ModuleId,
    NonEmptyStr,
    ReasonCode,
    RunId,
    SemanticVersion,
    Sha256Hex,
    StrictModel,
    UtcDateTime,
)


class ArtifactAbsenceState(StrEnum):
    NOT_PRODUCED = "NOT_PRODUCED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    EMPTY_VALID = "EMPTY_VALID"
    RESERVED = "RESERVED"


class ArtifactReference(StrictModel):
    artifact_id: ArtifactId
    artifact_type: NonEmptyStr
    schema_name: NonEmptyStr
    artifact_schema_version: SemanticVersion
    schema_sha256: Sha256Hex
    content_sha256: Sha256Hex
    producer_module_id: ModuleId
    run_id: RunId
    cycle_id: CycleId
    backtest_id: BacktestId
    event_time: UtcDateTime | None = None
    decision_time: UtcDateTime | None = None
    available_at: UtcDateTime
    computed_at: UtcDateTime
    maturity_at: UtcDateTime | None = None
    settlement_at: UtcDateTime | None = None
    location: NonEmptyStr
    availability: Availability = Availability.AVAILABLE
    record_count: int = Field(ge=0)
    grain: tuple[NonEmptyStr, ...] = ()
    parent_artifact_ids: tuple[ArtifactId, ...] = ()

    @model_validator(mode="after")
    def validate_clock_order(self) -> "ArtifactReference":
        if self.available_at > self.computed_at:
            raise ValueError("available_at must be <= computed_at")
        if self.event_time is not None and self.event_time > self.computed_at:
            raise ValueError("event_time must be <= computed_at")
        if self.decision_time is not None and self.decision_time > self.computed_at:
            raise ValueError("decision_time must be <= computed_at")
        if self.maturity_at is not None and self.event_time is not None:
            if self.maturity_at < self.event_time:
                raise ValueError("maturity_at must be >= event_time")
        if self.settlement_at is not None and self.event_time is not None:
            if self.settlement_at < self.event_time:
                raise ValueError("settlement_at must be >= event_time")
        if len(set(self.parent_artifact_ids)) != len(self.parent_artifact_ids):
            raise ValueError("parent_artifact_ids must be unique")
        return self


class ArtifactSlot(StrictModel):
    role: NonEmptyStr
    reference: ArtifactReference | None = None
    absence_state: ArtifactAbsenceState | None = None
    reason_codes: tuple[ReasonCode, ...] = ()

    @model_validator(mode="after")
    def validate_exactly_one_state(self) -> "ArtifactSlot":
        has_ref = self.reference is not None
        has_absence = self.absence_state is not None
        if has_ref == has_absence:
            raise ValueError("artifact slot requires exactly one of reference or absence_state")
        if has_absence and not self.reason_codes:
            raise ValueError("explicit absence requires reason_codes")
        if has_ref and self.reason_codes:
            raise ValueError("present artifact slot cannot contain absence reason_codes")
        return self
