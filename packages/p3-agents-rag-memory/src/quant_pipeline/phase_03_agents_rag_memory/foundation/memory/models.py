from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

Sha256 = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]
NonEmptyStr = Annotated[StrictStr, Field(min_length=1)]
PositiveInt = Annotated[StrictInt, Field(gt=0)]
NonNegativeInt = Annotated[StrictInt, Field(ge=0)]
UnitFloat = Annotated[StrictFloat, Field(ge=0.0, le=1.0)]


class FrozenContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


def parse_datetime(value: object) -> object:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return value
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return value


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include an explicit UTC offset")
    return value.astimezone(UTC)


class ArtifactStatus(StrEnum):
    READY = "READY"
    EMPTY_VALID = "EMPTY_VALID"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class MemoryType(StrEnum):
    EPISODIC = "EPISODIC"
    SEMANTIC = "SEMANTIC"
    PROCEDURAL = "PROCEDURAL"
    SOCIAL = "SOCIAL"


class VisibilityScope(StrEnum):
    SELF = "SELF"
    SOCIAL_VISIBLE = "SOCIAL_VISIBLE"
    PUBLIC = "PUBLIC"
    AUDIT_ONLY = "AUDIT_ONLY"


class FutureRecordPolicy(StrEnum):
    EXCLUDE_AND_REPORT = "EXCLUDE_AND_REPORT"
    BLOCK = "BLOCK"


class IndexMode(StrEnum):
    GENESIS = "GENESIS"
    REFRESH = "REFRESH"


class StorageMode(StrEnum):
    LOCAL_ATOMIC_JSONL = "LOCAL_ATOMIC_JSONL"
    ADAPTER_MANAGED = "ADAPTER_MANAGED"


class ArtifactRef(FrozenContractModel):
    artifact_id: NonEmptyStr
    artifact_type: NonEmptyStr
    content_hash: Sha256
    schema_id: NonEmptyStr | None = None
    schema_version: NonEmptyStr | None = None


class FactorWeights(FrozenContractModel):
    relevance: UnitFloat
    recency: UnitFloat
    importance: UnitFloat
    repetition: UnitFloat
    significance: UnitFloat

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "FactorWeights":
        total = self.relevance + self.recency + self.importance + self.repetition + self.significance
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"factor weights must sum to 1.0; got {total}")
        return self


class RetrievalBudgetConfig(FrozenContractModel):
    top_k_default: PositiveInt
    top_k_min: PositiveInt
    top_k_max: PositiveInt
    max_context_tokens: PositiveInt
    max_per_source: PositiveInt
    max_social_visible: NonNegativeInt

    @model_validator(mode="after")
    def validate_limits(self) -> "RetrievalBudgetConfig":
        if not self.top_k_min <= self.top_k_default <= self.top_k_max:
            raise ValueError("top_k_min <= top_k_default <= top_k_max is required")
        return self


class TypePolicyConfig(FrozenContractModel):
    memory_type: MemoryType
    enabled: StrictBool
    half_life_days: PositiveInt
    max_per_query: NonNegativeInt


class ScopePolicyConfig(FrozenContractModel):
    visibility_scope: VisibilityScope
    retrievable: StrictBool
    requires_relationship: StrictBool
    audit_only: StrictBool

    @model_validator(mode="after")
    def validate_audit_scope(self) -> "ScopePolicyConfig":
        if self.visibility_scope is VisibilityScope.AUDIT_ONLY:
            if self.retrievable or not self.audit_only:
                raise ValueError("AUDIT_ONLY must be non-retrievable and audit_only=true")
        elif self.audit_only:
            raise ValueError("audit_only=true is reserved for AUDIT_ONLY")
        return self


class MemoryAccessConfig(FrozenContractModel):
    schema_id: Literal["memory_access_config_s14.v1"] = "memory_access_config_s14.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    policy_version: NonEmptyStr
    formula_id: NonEmptyStr
    formula_version: NonEmptyStr
    factor_weights: FactorWeights
    budgets: RetrievalBudgetConfig
    type_policies: tuple[TypePolicyConfig, ...]
    scope_policies: tuple[ScopePolicyConfig, ...]
    pit_filter_required: Literal[True] = True
    audit_memory_separate: Literal[True] = True
    same_cycle_back_edge_forbidden: Literal[True] = True
    future_record_policy: FutureRecordPolicy

    @model_validator(mode="after")
    def cover_enums_exactly_once(self) -> "MemoryAccessConfig":
        types = [row.memory_type for row in self.type_policies]
        scopes = [row.visibility_scope for row in self.scope_policies]
        if set(types) != set(MemoryType) or len(types) != len(set(types)):
            raise ValueError("type_policies must cover every memory type exactly once")
        if set(scopes) != set(VisibilityScope) or len(scopes) != len(set(scopes)):
            raise ValueError("scope_policies must cover every visibility scope exactly once")
        return self


class PersonSchemaPolicyView(FrozenContractModel):
    schema_id: Literal["person_schema_policy_s14_view.v1"] = "person_schema_policy_s14_view.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    policy_id: NonEmptyStr
    person_schema_version: NonEmptyStr
    allowed_memory_types: tuple[MemoryType, ...]
    allowed_visibility_scopes: tuple[VisibilityScope, ...]
    content_hash: Sha256
    lineage_id: NonEmptyStr

    @model_validator(mode="after")
    def exact_memory_ontology(self) -> "PersonSchemaPolicyView":
        if set(self.allowed_memory_types) != set(MemoryType):
            raise ValueError("person policy must allow the canonical four memory types")
        if set(self.allowed_visibility_scopes) != set(VisibilityScope):
            raise ValueError("person policy must allow the canonical four visibility scopes")
        return self


class Phase3RunSnapshotView(FrozenContractModel):
    schema_id: Literal["phase3_run_snapshot.v1"] = "phase3_run_snapshot.v1"
    schema_version: NonEmptyStr
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    as_of: datetime
    evaluation_start: datetime
    evaluation_end: datetime
    lineage_id: NonEmptyStr
    snapshot_hash: Sha256

    @field_validator("as_of", "evaluation_start", "evaluation_end", mode="before")
    @classmethod
    def parse_dt(cls, value: object) -> object:
        return parse_datetime(value)

    @field_validator("as_of", "evaluation_start", "evaluation_end")
    @classmethod
    def normalize_dt(cls, value: datetime) -> datetime:
        return aware_utc(value)


class ScoreFormula(FrozenContractModel):
    formula_id: NonEmptyStr
    formula_version: NonEmptyStr
    factors: tuple[NonEmptyStr, ...]
    weights: FactorWeights
    recency_decay: Literal["EXPONENTIAL_HALF_LIFE"] = "EXPONENTIAL_HALF_LIFE"


class RetrievalBudget(FrozenContractModel):
    top_k_default: PositiveInt
    top_k_min: PositiveInt
    top_k_max: PositiveInt
    max_context_tokens: PositiveInt
    max_per_source: PositiveInt
    max_social_visible: NonNegativeInt


class TypePolicy(FrozenContractModel):
    memory_type: MemoryType
    enabled: StrictBool
    half_life_days: PositiveInt
    max_per_query: NonNegativeInt


class ScopePolicy(FrozenContractModel):
    visibility_scope: VisibilityScope
    retrievable: StrictBool
    requires_relationship: StrictBool
    audit_only: StrictBool


class TemporalMemoryPolicy(FrozenContractModel):
    pit_filter_required: Literal[True] = True
    same_cycle_back_edge_forbidden: Literal[True] = True
    future_record_policy: FutureRecordPolicy


class MemoryAccessPolicy(FrozenContractModel):
    schema_id: Literal["memory_access_policy.v2"] = "memory_access_policy.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: NonEmptyStr
    module_id: Literal["P3.S14.M01"] = "P3.S14.M01"
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    as_of_time: datetime
    policy_id: NonEmptyStr
    policy_version: NonEmptyStr
    person_schema_policy_hash: Sha256
    score_formula: ScoreFormula
    budgets: RetrievalBudget
    type_policies: tuple[TypePolicy, ...]
    scope_policies: tuple[ScopePolicy, ...]
    temporal_policy: TemporalMemoryPolicy
    audit_memory_separate: Literal[True] = True
    status: Literal[ArtifactStatus.READY] = ArtifactStatus.READY
    content_hash: Sha256
    lineage_id: NonEmptyStr

    @field_validator("as_of_time", mode="before")
    @classmethod
    def parse_as_of(cls, value: object) -> object:
        return parse_datetime(value)

    @field_validator("as_of_time")
    @classmethod
    def normalize_as_of(cls, value: datetime) -> datetime:
        return aware_utc(value)


class MemoryRecord(FrozenContractModel):
    memory_id: NonEmptyStr
    person_id: NonEmptyStr
    memory_type: MemoryType
    visibility_scope: VisibilityScope
    created_at: datetime
    available_at: datetime
    content_ref: ArtifactRef
    importance: UnitFloat
    repetition: UnitFloat
    significance: UnitFloat

    @field_validator("created_at", "available_at", mode="before")
    @classmethod
    def parse_dt(cls, value: object) -> object:
        return parse_datetime(value)

    @field_validator("created_at", "available_at")
    @classmethod
    def normalize_dt(cls, value: datetime) -> datetime:
        return aware_utc(value)

    @model_validator(mode="after")
    def availability_not_before_creation(self) -> "MemoryRecord":
        if self.available_at < self.created_at:
            raise ValueError("available_at cannot precede created_at")
        return self


class CurrentMemoryState(FrozenContractModel):
    schema_id: Literal["current_memory_state.v2"] = "current_memory_state.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: NonEmptyStr
    module_id: Literal["P3.S11.M03"] = "P3.S11.M03"
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    cycle_id: NonEmptyStr
    cycle_number: PositiveInt
    as_of_time: datetime
    source_state_hash: Sha256
    records: tuple[MemoryRecord, ...]
    content_hash: Sha256
    lineage_id: NonEmptyStr

    @field_validator("as_of_time", mode="before")
    @classmethod
    def parse_as_of(cls, value: object) -> object:
        return parse_datetime(value)

    @field_validator("as_of_time")
    @classmethod
    def normalize_as_of(cls, value: datetime) -> datetime:
        return aware_utc(value)


class RetrievalConfig(FrozenContractModel):
    schema_id: Literal["memory_retrieval_config_s14.v1"] = "memory_retrieval_config_s14.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    adapter_id: NonEmptyStr
    adapter_version: NonEmptyStr
    index_version: NonEmptyStr
    storage_mode: StorageMode
    hash_algorithm: Literal["sha256"] = "sha256"
    partition_fields: tuple[Literal["person_id", "memory_type", "visibility_scope"], ...]
    max_records: PositiveInt
    allow_degraded_backend: StrictBool

    @model_validator(mode="after")
    def exact_partition_fields(self) -> "RetrievalConfig":
        expected = ("person_id", "memory_type", "visibility_scope")
        if tuple(self.partition_fields) != expected:
            raise ValueError(f"partition_fields must equal {expected}")
        return self


class IndexEntry(FrozenContractModel):
    memory_id: NonEmptyStr
    person_id: NonEmptyStr
    memory_type: MemoryType
    visibility_scope: VisibilityScope
    available_at: datetime
    content_ref: ArtifactRef
    importance: UnitFloat
    repetition: UnitFloat
    significance: UnitFloat

    @field_validator("available_at", mode="before")
    @classmethod
    def parse_dt(cls, value: object) -> object:
        return parse_datetime(value)

    @field_validator("available_at")
    @classmethod
    def normalize_dt(cls, value: datetime) -> datetime:
        return aware_utc(value)


class IndexPartitionRequest(FrozenContractModel):
    partition_key: NonEmptyStr
    entries: tuple[IndexEntry, ...]
    partition_hash: Sha256


class IndexPartitionResult(FrozenContractModel):
    partition_key: NonEmptyStr
    index_ref: NonEmptyStr
    record_count: NonNegativeInt
    partition_hash: Sha256
    storage_hash: Sha256


class MemoryIndexPartition(FrozenContractModel):
    partition_key: NonEmptyStr
    person_id: NonEmptyStr
    memory_type: MemoryType
    visibility_scope: VisibilityScope
    record_count: NonNegativeInt
    partition_hash: Sha256
    index_ref: NonEmptyStr
    storage_hash: Sha256
    retrievable: StrictBool


class ExclusionSummary(FrozenContractModel):
    future_record_count: NonNegativeInt
    audit_only_record_count: NonNegativeInt
    disabled_type_record_count: NonNegativeInt
    excluded_memory_ids_hash: Sha256


class MemoryIndexManifest(FrozenContractModel):
    schema_id: Literal["memory_index_manifest.v2"] = "memory_index_manifest.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: NonEmptyStr
    module_id: Literal["P3.S14.M02"] = "P3.S14.M02"
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    cycle_id: NonEmptyStr
    cycle_number: PositiveInt
    as_of_time: datetime
    mode: IndexMode
    memory_state_hash: Sha256
    policy_hash: Sha256
    retrieval_config_hash: Sha256
    adapter_id: NonEmptyStr
    adapter_version: NonEmptyStr
    index_version: NonEmptyStr
    partitions: tuple[MemoryIndexPartition, ...]
    total_input_records: NonNegativeInt
    total_indexed_records: NonNegativeInt
    exclusions: ExclusionSummary
    status: ArtifactStatus
    content_hash: Sha256
    lineage_id: NonEmptyStr

    @field_validator("as_of_time", mode="before")
    @classmethod
    def parse_as_of(cls, value: object) -> object:
        return parse_datetime(value)

    @field_validator("as_of_time")
    @classmethod
    def normalize_as_of(cls, value: datetime) -> datetime:
        return aware_utc(value)
