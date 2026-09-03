"""Canonical execution and artifact contracts for P5."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
        allow_inf_nan=False,
    )


class ExecutionMode(StrEnum):
    OFFLINE_TRAINING = "OFFLINE_TRAINING"
    RUNTIME_INFERENCE = "RUNTIME_INFERENCE"
    VALIDATION = "VALIDATION"
    PUBLICATION = "PUBLICATION"
    INTEGRATION_REPLAY = "INTEGRATION_REPLAY"


class ModuleAction(StrEnum):
    RUN = "RUN"
    FIT = "FIT"
    PREDICT = "PREDICT"
    VALIDATE = "VALIDATE"
    PUBLISH = "PUBLISH"


class ModuleStatus(StrEnum):
    SUCCESS = "SUCCESS"
    DEGRADED = "DEGRADED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ArtifactReference(FrozenModel):
    artifact_id: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    storage_uri: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: str = Field(default="1.0.0", min_length=1)
    row_count: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("storage_uri")
    @classmethod
    def safe_relative_uri(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("storage_uri must be a safe relative path")
        return value


class ModuleRequest(FrozenModel):
    module_id: str = Field(pattern=r"^P5\.S[1-9]\.M\d{2}$")
    action: ModuleAction
    payload: dict[str, Any] = Field(default_factory=dict)
    input_artifacts: dict[str, ArtifactReference] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)


class ErrorRecord(FrozenModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class ModuleResult(FrozenModel):
    module_id: str
    status: ModuleStatus
    outputs: dict[str, ArtifactReference] = Field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    errors: tuple[ErrorRecord, ...] = ()
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_result(self) -> "ModuleResult":
        successful = {ModuleStatus.SUCCESS, ModuleStatus.DEGRADED}
        if self.status in successful and not self.outputs:
            raise ValueError("successful or degraded result requires at least one output")
        if self.status is ModuleStatus.DEGRADED and not self.warnings:
            raise ValueError("degraded result requires at least one warning")
        if self.status is ModuleStatus.SUCCESS and (self.errors or self.warnings):
            raise ValueError("successful result cannot contain warnings or errors")
        if self.status in {ModuleStatus.FAILED, ModuleStatus.REJECTED} and not self.errors:
            raise ValueError("failed or rejected result requires errors")
        if self.status in {ModuleStatus.SKIPPED, ModuleStatus.FAILED, ModuleStatus.REJECTED} and self.outputs:
            raise ValueError("skipped, failed or rejected result cannot publish outputs")
        return self


class RunIdentity(FrozenModel):
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    generated_at: datetime
    seed: int = 0
    pipeline_version: str = "P5-RC34.1-CONTRACT-CLOSURE-RC4"

    @field_validator("as_of_time", "generated_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_clock(self) -> "RunIdentity":
        if self.generated_at < self.as_of_time:
            raise ValueError("generated_at cannot precede as_of_time")
        return self


class ModuleDescriptor(FrozenModel):
    module_id: str = Field(pattern=r"^P5\.S[1-9]\.M\d{2}$")
    name: str = Field(min_length=1)
    subphase_id: str = Field(pattern=r"^P5\.S[1-9]$")
    required_inputs: tuple[str, ...] = ()
    optional_inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = Field(min_length=1)
    allowed_actions: tuple[ModuleAction, ...] = Field(min_length=1)
    allowed_modes: tuple[ExecutionMode, ...] = Field(min_length=1)
    capability: str = "CORE"

    @model_validator(mode="after")
    def validate_names(self) -> "ModuleDescriptor":
        all_inputs = self.required_inputs + self.optional_inputs
        if len(all_inputs) != len(set(all_inputs)):
            raise ValueError("module input names must be unique")
        if len(self.outputs) != len(set(self.outputs)):
            raise ValueError("module output names must be unique")
        return self


class HandlerOutcome(FrozenModel):
    values: tuple[Any, ...]
    status: ModuleStatus = ModuleStatus.SUCCESS
    warnings: tuple[str, ...] = ()
    diagnostics: dict[str, Any] = Field(default_factory=dict)
