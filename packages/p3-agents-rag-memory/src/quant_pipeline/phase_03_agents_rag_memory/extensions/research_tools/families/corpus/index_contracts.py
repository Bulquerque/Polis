from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import ContractModel

from .types import (
    CapabilityStatus,
    CorpusMode,
    NonEmptyStr,
    Probability,
    QualificationStatus,
    Sha256,
    aware_utc,
)


class CorpusArtifactRef(ContractModel):
    artifact_type: NonEmptyStr
    uri: NonEmptyStr
    content_hash: Sha256
    media_type: NonEmptyStr
    size_bytes: int = Field(ge=0)
    record_count: int | None = Field(default=None, ge=0)
    format_version: NonEmptyStr


class CapabilityReadiness(ContractModel):
    capability_id: NonEmptyStr
    status: CapabilityStatus
    qualification_status: NonEmptyStr
    provider_id: str | None = None
    model_id: str | None = None
    model_revision: str | None = None
    snapshot_id: str | None = None
    supported_filters: tuple[NonEmptyStr, ...] = ()
    reason_code: str | None = None

    @model_validator(mode="after")
    def filters_are_unique(self) -> "CapabilityReadiness":
        if len(self.supported_filters) != len(set(self.supported_filters)):
            raise ValueError("supported_filters must be unique")
        return self


class CorpusIndexSnapshot(ContractModel):
    schema_id: Literal["corpus_index_snapshot.s35.v1"] = "corpus_index_snapshot.s35.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    artifact_id: NonEmptyStr
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    as_of_time: datetime
    retrieval_manifest_id: NonEmptyStr
    retrieval_manifest_hash: Sha256
    rag_index_artifact_hash: Sha256
    chunk_schema_id: NonEmptyStr
    chunk_count: int = Field(ge=0)
    chunk_catalog: CorpusArtifactRef
    keyword_index: CorpusArtifactRef
    vector_index: CorpusArtifactRef | None = None
    capabilities: tuple[CapabilityReadiness, ...]
    required_metadata_filters: tuple[NonEmptyStr, ...]
    configuration_hash: Sha256
    provider_fingerprints: dict[str, NonEmptyStr]
    fallback_strategy: str | None = None
    issues: tuple[str, ...] = ()
    content_hash: Sha256

    _as_of = field_validator("as_of_time")(aware_utc)

    @model_validator(mode="after")
    def validate_capabilities_and_filters(self) -> "CorpusIndexSnapshot":
        capability_ids = [item.capability_id for item in self.capabilities]
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("capability IDs must be unique")
        missing = sorted(
            {"keyword_retrieval", "available_at_filtering"} - set(capability_ids)
        )
        if missing:
            raise ValueError(f"missing required corpus capabilities: {missing}")
        if len(self.required_metadata_filters) != len(set(self.required_metadata_filters)):
            raise ValueError("required_metadata_filters must be unique")
        if self.chunk_catalog.record_count not in {None, self.chunk_count}:
            raise ValueError("chunk catalog record_count must match chunk_count")
        return self


class CorpusIndexReadinessReport(ContractModel):
    schema_id: Literal["corpus_index_readiness_report.s35.v1"] = (
        "corpus_index_readiness_report.s35.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot_id: NonEmptyStr
    status: QualificationStatus
    lexical_ready: bool
    semantic_ready: bool
    reranker_ready: bool
    point_in_time_filter_ready: bool
    chunk_count: int = Field(ge=0)
    reason_codes: tuple[NonEmptyStr, ...] = ()
    content_hash: Sha256

    @model_validator(mode="after")
    def readiness_is_consistent(self) -> "CorpusIndexReadinessReport":
        if self.status is QualificationStatus.QUALIFIED_LOCAL:
            if not self.lexical_ready or not self.point_in_time_filter_ready:
                raise ValueError("qualified corpus requires lexical and PIT readiness")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason_codes must be unique")
        return self


class ModePolicy(ContractModel):
    mode_id: CorpusMode
    max_results: int = Field(gt=0, le=100)
    max_internal_subqueries: int = Field(gt=0, le=8)
    max_internal_work_units: int = Field(gt=0, le=100)
    require_semantic: bool = False
    allow_semantic: bool = False
    allow_reranker: bool = False
    minimum_source_families: int = Field(default=1, ge=1, le=10)
    require_counterevidence: bool = False
    require_version_graph: bool = False
    coverage_floor: Probability = 0.0
    downgrade_targets: tuple[CorpusMode, ...] = ()

    @model_validator(mode="after")
    def mode_is_consistent(self) -> "ModePolicy":
        if self.require_semantic and not self.allow_semantic:
            raise ValueError("require_semantic implies allow_semantic")
        if self.mode_id in self.downgrade_targets:
            raise ValueError("mode cannot downgrade to itself")
        if len(self.downgrade_targets) != len(set(self.downgrade_targets)):
            raise ValueError("downgrade targets must be unique")
        return self


class CorpusRetrievalPolicy(ContractModel):
    schema_id: Literal["corpus_retrieval_policy.s35.v1"] = "corpus_retrieval_policy.s35.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    policy_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    lexical_algorithm: Literal["BM25_V1"] = "BM25_V1"
    fusion_algorithm: Literal["RRF_V1"] = "RRF_V1"
    rrf_constant: int = Field(default=60, ge=1, le=1000)
    bm25_k1: float = Field(default=1.5, gt=0.0, le=5.0)
    bm25_b: float = Field(default=0.75, ge=0.0, le=1.0)
    deduplicate_by_content_hash: Literal[True] = True
    filter_point_in_time_before_scoring: Literal[True] = True
    modes: tuple[ModePolicy, ...]
    content_hash: Sha256

    @model_validator(mode="after")
    def modes_are_complete_and_unique(self) -> "CorpusRetrievalPolicy":
        ids = [item.mode_id for item in self.modes]
        if len(ids) != len(set(ids)):
            raise ValueError("retrieval modes must be unique")
        missing = set(CorpusMode) - set(ids)
        if missing:
            raise ValueError(f"retrieval policy is missing modes: {sorted(missing)}")
        rank = {
            CorpusMode.LOOKUP: 1,
            CorpusMode.STANDARD: 2,
            CorpusMode.TRIANGULATED: 3,
            CorpusMode.FORENSIC: 4,
        }
        for mode in self.modes:
            if any(rank[target] >= rank[mode.mode_id] for target in mode.downgrade_targets):
                raise ValueError("downgrade target must be shallower than source mode")
        return self

    def mode(self, mode_id: CorpusMode) -> ModePolicy:
        for item in self.modes:
            if item.mode_id is mode_id:
                return item
        raise KeyError(mode_id)


class CorpusInternalWorkBudget(ContractModel):
    schema_id: Literal["corpus_internal_work_budget.s35.v1"] = (
        "corpus_internal_work_budget.s35.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    policy_id: NonEmptyStr
    work_units_by_mode: dict[CorpusMode, int]
    subqueries_by_mode: dict[CorpusMode, int]
    visible_s21_call_cost: Literal[1] = 1
    content_hash: Sha256

    @model_validator(mode="after")
    def budgets_cover_every_mode(self) -> "CorpusInternalWorkBudget":
        expected = set(CorpusMode)
        if set(self.work_units_by_mode) != expected:
            raise ValueError("work_units_by_mode must cover every corpus mode")
        if set(self.subqueries_by_mode) != expected:
            raise ValueError("subqueries_by_mode must cover every corpus mode")
        if any(value <= 0 for value in self.work_units_by_mode.values()):
            raise ValueError("work units must be positive")
        if any(value <= 0 for value in self.subqueries_by_mode.values()):
            raise ValueError("subquery limits must be positive")
        return self


def validate_snapshot_readiness_pair(
    snapshot: CorpusIndexSnapshot, readiness: CorpusIndexReadinessReport
) -> None:
    """Fail closed when the snapshot and its readiness report disagree."""
    if snapshot.snapshot_id != readiness.snapshot_id:
        raise ValueError("corpus snapshot/readiness snapshot_id mismatch")
    if snapshot.chunk_count != readiness.chunk_count:
        raise ValueError("corpus snapshot/readiness chunk_count mismatch")
    capabilities = {item.capability_id: item.status for item in snapshot.capabilities}
    lexical = capabilities.get("keyword_retrieval") is CapabilityStatus.READY
    pit = capabilities.get("available_at_filtering") is CapabilityStatus.READY
    semantic = capabilities.get("semantic_retrieval") is CapabilityStatus.READY
    reranker = capabilities.get("reranker") is CapabilityStatus.READY
    if readiness.lexical_ready != lexical:
        raise ValueError("corpus lexical readiness contradicts snapshot capabilities")
    if readiness.point_in_time_filter_ready != pit:
        raise ValueError("corpus PIT readiness contradicts snapshot capabilities")
    if readiness.semantic_ready and not semantic:
        raise ValueError("corpus semantic readiness lacks a READY semantic_retrieval capability")
    if readiness.reranker_ready and not reranker:
        raise ValueError("corpus reranker readiness lacks a READY reranker capability")
