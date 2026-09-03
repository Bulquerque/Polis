"""Typed boundary models for P7.S1."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, field_validator

SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Version = Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class ModuleContext(StrictModel):
    pipeline_version: str
    run_id: str
    cycle_id: str
    decision_time: AwareDatetime
    available_at: AwareDatetime | None = None
    created_at: AwareDatetime
    lineage_id: str


class ManifestArtifactRef(StrictModel):
    artifact_name: str
    artifact_id: str
    content_sha256: SHA256
    schema_version: Version
    record_count: int = Field(ge=0)
    required: bool = True
    grain: str


class P6HandoffManifest(StrictModel):
    manifest_id: str
    contract_version: Version
    schema_version: Version
    producer_phase: Literal["P6"]
    destination_phase: Literal["P7"]
    pipeline_version: str
    run_id: str
    cycle_id: str
    decision_time: AwareDatetime
    created_at: AwareDatetime
    artifacts: tuple[ManifestArtifactRef, ...]

    @field_validator("artifacts")
    @classmethod
    def unique_artifact_names(cls, value: tuple[ManifestArtifactRef, ...]) -> tuple[ManifestArtifactRef, ...]:
        names = [item.artifact_name for item in value]
        if len(names) != len(set(names)):
            raise ValueError("manifest artifact names must be unique")
        return value


class ArtifactEnvelope(StrictModel):
    artifact_id: str
    artifact_name: str
    schema_version: Version
    producer_phase: str
    producer_module_id: str
    destination_phase: str
    pipeline_version: str
    run_id: str
    cycle_id: str
    decision_time: AwareDatetime
    available_at: AwareDatetime
    created_at: AwareDatetime
    content_sha256: SHA256
    record_count: int = Field(ge=0)
    grain: str
    lineage_id: str
    capability_status: Literal["AVAILABLE", "UNAVAILABLE", "DEGRADED"] = "AVAILABLE"
    records: tuple[dict[str, JsonValue], ...]

    @field_validator("records")
    @classmethod
    def records_match_count(cls, value: tuple[dict[str, JsonValue], ...], info):
        expected = info.data.get("record_count")
        if expected is not None and len(value) != expected:
            raise ValueError("record_count does not match records")
        return value

    def hash_payload(self) -> dict[str, JsonValue]:
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        return payload


class ModuleConfig(StrictModel):
    context: ModuleContext
    policy: dict[str, JsonValue] = Field(default_factory=dict)


class ModuleResponse(StrictModel):
    module_id: str
    status: Literal["PASS", "DEGRADED", "SKIPPED"]
    outputs: dict[str, dict[str, JsonValue]]
    issues: tuple[dict[str, JsonValue], ...] = ()
    receipt: dict[str, JsonValue]


class FeedbackManifest(StrictModel):
    manifest_id: str
    schema_version: Version
    producer_phase: Literal["P9"]
    destination_phase: Literal["P7"]
    source_cycle_id: str
    source_cycle_sequence: int = Field(ge=0)
    target_cycle_id: str
    target_cycle_sequence: int = Field(ge=0)
    promotion_status: Literal["PROMOTED", "DRAFT", "REJECTED"]
    report_artifact_id: str
    report_content_sha256: SHA256
    decision_time: AwareDatetime
    created_at: AwareDatetime


class FeedbackAdjustment(StrictModel):
    adjustment_type: Literal[
        "ELIGIBILITY_THRESHOLD",
        "MODEL_ELIGIBILITY",
        "POLICY_PARAMETER_BOUND",
        "DEPRECATION_NOTICE",
    ]
    parameter: str
    value: JsonValue


class FeedbackRecord(StrictModel):
    feedback_id: str
    source_cycle_id: str
    source_cycle_sequence: int = Field(ge=0)
    target_cycle_id: str
    target_cycle_sequence: int = Field(ge=0)
    promotion_status: Literal["PROMOTED", "DRAFT", "REJECTED"]
    scope: dict[str, JsonValue]
    evidence_ids: tuple[str, ...]
    valid_from_cycle_sequence: int = Field(ge=0)
    expires_at: AwareDatetime | None = None
    adjustments: tuple[FeedbackAdjustment, ...] = ()

    @field_validator("evidence_ids")
    @classmethod
    def evidence_required(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(not item for item in value):
            raise ValueError("evidence_ids must be non-empty")
        return value


def major(version: str) -> int:
    return int(version.split(".", maxsplit=1)[0])
