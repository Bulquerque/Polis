from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

Sha256 = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]
NonEmptyStr = Annotated[StrictStr, Field(min_length=1)]


class FrozenContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class WarmupMode(StrEnum):
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    GENESIS_ONLY = "GENESIS_ONLY"


class ValidationStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"


class DatasetPartition(StrEnum):
    WARMUP = "WARMUP"
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    EVALUATION = "EVALUATION"
    HOLDOUT = "HOLDOUT"
    TEST = "TEST"


class ArtifactRef(FrozenContractModel):
    artifact_id: NonEmptyStr
    artifact_type: NonEmptyStr
    content_hash: Sha256
    schema_id: NonEmptyStr | None = None
    schema_version: NonEmptyStr | None = None


class RecordLineage(FrozenContractModel):
    lineage_id: NonEmptyStr
    source_artifact_ids: tuple[NonEmptyStr, ...] = ()
    parent_lineage_ids: tuple[NonEmptyStr, ...] = ()
    holdout_refs: tuple[NonEmptyStr, ...] = ()


class HistoryRecord(FrozenContractModel):
    history_record_id: NonEmptyStr
    event_id: NonEmptyStr
    source_id: NonEmptyStr
    partition: DatasetPartition
    event_time: datetime
    effective_time: datetime | None = None
    available_at: datetime
    ingested_at: datetime
    payload_ref: ArtifactRef
    underlyings: tuple[NonEmptyStr, ...] = ()
    propositions: tuple[NonEmptyStr, ...] = ()
    lineage: RecordLineage

    @field_validator("event_time", "effective_time", "available_at", "ingested_at", mode="before")
    @classmethod
    def parse_datetime(cls, value: object) -> object:
        if value is None or isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            return value
        normalized = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return value

    @field_validator("event_time", "effective_time", "available_at", "ingested_at")
    @classmethod
    def require_aware_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must include an explicit UTC offset")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_ingestion_order(self) -> "HistoryRecord":
        if self.ingested_at < self.available_at:
            raise ValueError("ingested_at must be greater than or equal to available_at")
        return self


class WarmupHistoryBundle(FrozenContractModel):
    schema_id: Literal["warmup_history_bundle.v1"] = "warmup_history_bundle.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    history_id: NonEmptyStr
    mode: WarmupMode
    records: tuple[HistoryRecord, ...]
    lineage_id: NonEmptyStr
    source_bundle_refs: tuple[ArtifactRef, ...] = ()

    @model_validator(mode="after")
    def validate_mode_cardinality(self) -> "WarmupHistoryBundle":
        if self.mode is WarmupMode.GENESIS_ONLY and self.records:
            raise ValueError("GENESIS_ONLY requires an empty records collection")
        if self.mode is WarmupMode.HISTORICAL_REPLAY and not self.records:
            raise ValueError("HISTORICAL_REPLAY requires at least one record")
        return self


class EvaluationWindowConfig(FrozenContractModel):
    schema_id: Literal["evaluation_window_config.s9.v1"]
    schema_version: Literal["1.0.0"]
    warmup_start: datetime | None = None
    evaluation_start: datetime | None = None
    evaluation_end: datetime | None = None
    holdout_start: datetime | None = None
    holdout_end: datetime | None = None
    holdout_artifact_ids: tuple[NonEmptyStr, ...] = ()
    allowed_partitions: tuple[DatasetPartition, ...] = (
        DatasetPartition.WARMUP,
        DatasetPartition.TRAIN,
    )
    forbidden_partitions: tuple[DatasetPartition, ...] = (
        DatasetPartition.EVALUATION,
        DatasetPartition.HOLDOUT,
        DatasetPartition.TEST,
    )
    warmup_end_strictly_before_evaluation: StrictBool
    final_holdout_blind: StrictBool
    timezone: Literal["UTC"]
    boundary_rule: Literal[
        "available_at_equal_as_of_allowed",
        "available_at_strictly_before_as_of",
    ]
    allow_degraded_history: StrictBool = False
    max_records: Annotated[StrictInt, Field(ge=0, le=10_000_000)] = 1_000_000

    @field_validator(
        "warmup_start",
        "evaluation_start",
        "evaluation_end",
        "holdout_start",
        "holdout_end",
        mode="before",
    )
    @classmethod
    def parse_datetime(cls, value: object) -> object:
        if value is None or isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            return value
        normalized = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return value

    @field_validator(
        "warmup_start",
        "evaluation_start",
        "evaluation_end",
        "holdout_start",
        "holdout_end",
    )
    @classmethod
    def require_aware_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must include an explicit UTC offset")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_windows(self) -> "EvaluationWindowConfig":
        if self.evaluation_start and self.evaluation_end:
            if self.evaluation_end <= self.evaluation_start:
                raise ValueError("evaluation_end must be after evaluation_start")
        if bool(self.holdout_start) is not bool(self.holdout_end):
            raise ValueError("holdout_start and holdout_end must be provided together")
        if self.holdout_start and self.holdout_end and self.holdout_end <= self.holdout_start:
            raise ValueError("holdout_end must be after holdout_start")
        if set(self.allowed_partitions) & set(self.forbidden_partitions):
            raise ValueError("allowed_partitions and forbidden_partitions must be disjoint")
        return self


class Phase3RunSnapshotView(FrozenContractModel):
    schema_id: NonEmptyStr = "phase3_run_snapshot.v1"
    schema_version: NonEmptyStr
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    as_of: datetime = Field(validation_alias=AliasChoices("as_of", "as_of_time"))
    evaluation_start: datetime | None = None
    evaluation_end: datetime | None = None
    lineage_id: NonEmptyStr
    snapshot_hash: Sha256 | None = None

    @field_validator("as_of", "evaluation_start", "evaluation_end", mode="before")
    @classmethod
    def parse_datetime(cls, value: object) -> object:
        if value is None or isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            return value
        normalized = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return value

    @field_validator("as_of", "evaluation_start", "evaluation_end")
    @classmethod
    def require_aware_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must include an explicit UTC offset")
        return value.astimezone(UTC)


class OutputLineage(FrozenContractModel):
    lineage_id: NonEmptyStr
    input_history_id: NonEmptyStr
    input_history_hash: Sha256
    input_snapshot_id: NonEmptyStr
    input_snapshot_hash: Sha256 | None = None
    source_artifact_ids: tuple[NonEmptyStr, ...]
    source_lineage_ids: tuple[NonEmptyStr, ...]


class ValidationIssueModel(FrozenContractModel):
    code: NonEmptyStr
    severity: Literal["INFO", "WARNING"]
    message: NonEmptyStr
    path: NonEmptyStr


class ValidationSummary(FrozenContractModel):
    input_record_count: StrictInt
    output_record_count: StrictInt
    unique_event_count: StrictInt
    unique_source_count: StrictInt
    earliest_available_at: datetime | None
    latest_available_at: datetime | None
    rejected_record_count: Literal[0] = 0


class ValidatedWarmupHistory(FrozenContractModel):
    schema_id: Literal["validated_warmup_history.v1"] = "validated_warmup_history.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    artifact_id: NonEmptyStr
    module_id: Literal["P3.S9.M01"] = "P3.S9.M01"
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    as_of: datetime
    mode: WarmupMode
    status: ValidationStatus
    evaluation_start: datetime
    warmup_start: datetime | None
    warmup_end: datetime | None
    records: tuple[HistoryRecord, ...]
    history_hash: Sha256
    lineage: OutputLineage
    validation_summary: ValidationSummary
    issues: tuple[ValidationIssueModel, ...] = ()
