"""P3_INTEGRATION_CONTRACT_PACK_V2.

These models define only the boundary between foundation (S1-S16), runtime
(S17-S31), warm-up replay and next-cycle restoration. Rich domain artifacts
remain owned by their producing capability.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .base import ArtifactPointer, LineageRecord, ReadinessStatus, RunIdentity, StrictModel

NonEmptyStr = Annotated[str, Field(min_length=1)]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]

CONTRACT_PACK_ID = "P3_INTEGRATION_CONTRACT_PACK_V2"
CONTRACT_PACK_VERSION = "2.0.0"


class CycleExecutionMode(StrEnum):
    WARMUP_REPLAY = "WARMUP_REPLAY"
    LIVE = "LIVE"
    REPLAY = "REPLAY"
    DRY_RUN = "DRY_RUN"


class CycleExecutionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class StateSource(StrEnum):
    GENESIS = "GENESIS"
    WARMUP_CHECKPOINT = "WARMUP_CHECKPOINT"
    PRIOR_CYCLE = "PRIOR_CYCLE"


class CapabilityFlags(StrictModel):
    allow_live_providers: bool = False
    allow_tool_execution: bool = False
    emit_p4_outputs: bool = False
    emit_p9_outputs: bool = False
    require_frozen_provider_responses: bool = True

    @model_validator(mode="after")
    def warmup_safe_defaults(self) -> "CapabilityFlags":
        if self.require_frozen_provider_responses and self.allow_live_providers:
            raise ValueError("frozen-provider mode cannot allow live providers")
        return self


class BudgetLimits(StrictModel):
    max_llm_calls: int = Field(default=0, ge=0)
    max_tool_calls: int = Field(default=0, ge=0)
    max_retrieval_calls: int = Field(default=0, ge=0)
    max_total_tokens: int = Field(default=0, ge=0)


class FoundationGovernanceView(StrictModel):
    artifact_name: Literal["foundation_governance_view"] = "foundation_governance_view"
    schema_id: Literal["foundation_governance_view.v1"] = "foundation_governance_view.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    artifact_id: NonEmptyStr
    identity: RunIdentity
    pit_context_ref: ArtifactPointer
    run_snapshot_ref: ArtifactPointer
    model_cutoff_view_ref: ArtifactPointer
    active_feedback_ref: ArtifactPointer
    person_policy_ref: ArtifactPointer
    tag_registry_ref: ArtifactPointer
    selected_model_ref: NonEmptyStr
    content_hash: Sha256
    lineage: LineageRecord


class CapabilityScore(StrictModel):
    capability_id: NonEmptyStr
    score: UnitFloat


class PopulationPersonRuntimeRecord(StrictModel):
    person_id: NonEmptyStr
    economic_role: NonEmptyStr
    role_family: NonEmptyStr
    representation_weight: UnitFloat
    deterministic_seed: int = Field(ge=0)
    availability_constraints: tuple[NonEmptyStr, ...] = ()
    capabilities: tuple[CapabilityScore, ...] = ()
    structural_profile_ref: ArtifactPointer


class PopulationRuntimeView(StrictModel):
    artifact_name: Literal["population_runtime_view"] = "population_runtime_view"
    schema_id: Literal["population_runtime_view.v1"] = "population_runtime_view.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    artifact_id: NonEmptyStr
    population_id: NonEmptyStr
    records: tuple[PopulationPersonRuntimeRecord, ...]
    coverage_ref: ArtifactPointer
    source_manifest_ref: ArtifactPointer
    status: ReadinessStatus
    content_hash: Sha256
    lineage: LineageRecord

    @model_validator(mode="after")
    def validate_population(self) -> "PopulationRuntimeView":
        ids = [item.person_id for item in self.records]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("population records must be non-empty and unique")
        if abs(sum(item.representation_weight for item in self.records) - 1.0) > 1e-8:
            raise ValueError("representation weights must sum to 1")
        return self


class DomainTrustRecord(StrictModel):
    domain_id: NonEmptyStr
    value: UnitFloat


class SocialGraphRuntimeRecord(StrictModel):
    edge_id: NonEmptyStr
    source_person_id: NonEmptyStr
    target_person_id: NonEmptyStr
    relationship_type: NonEmptyStr
    strength: UnitFloat
    global_trust: UnitFloat
    domain_trust: tuple[DomainTrustRecord, ...]
    influence: UnitFloat
    interaction_frequency: UnitFloat
    selection_probability: UnitFloat
    valid_from: datetime
    valid_to: datetime | None = None
    provenance_ref: NonEmptyStr

    @field_validator("valid_from", "valid_to")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("graph validity timestamps must be timezone-aware")
        return value.astimezone(UTC)


class SocialGraphRuntimeView(StrictModel):
    artifact_name: Literal["social_graph_runtime_view"] = "social_graph_runtime_view"
    schema_id: Literal["social_graph_runtime_view.v1"] = "social_graph_runtime_view.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    artifact_id: NonEmptyStr
    population_id: NonEmptyStr
    records: tuple[SocialGraphRuntimeRecord, ...]
    source_graph_ref: ArtifactPointer
    content_hash: Sha256
    lineage: LineageRecord


class StateRuntimeView(StrictModel):
    artifact_name: Literal["state_runtime_view"] = "state_runtime_view"
    schema_id: Literal["state_runtime_view.v1"] = "state_runtime_view.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    artifact_id: NonEmptyStr
    source: StateSource
    current_person_state_ref: ArtifactPointer
    current_belief_state_ref: ArtifactPointer
    current_memory_state_ref: ArtifactPointer
    current_social_graph_ref: ArtifactPointer
    pending_stimuli_ref: ArtifactPointer
    belief_commitments_ref: ArtifactPointer
    content_hash: Sha256
    lineage: LineageRecord


class KnowledgeRuntimeView(StrictModel):
    artifact_name: Literal["knowledge_runtime_view"] = "knowledge_runtime_view"
    schema_id: Literal["knowledge_runtime_view.v1"] = "knowledge_runtime_view.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    artifact_id: NonEmptyStr
    rag_index_ref: ArtifactPointer
    retrieval_manifest_ref: ArtifactPointer
    graph_rag_ref: ArtifactPointer
    graph_evidence_ref: ArtifactPointer
    retrieval_port_id: NonEmptyStr
    graph_query_port_id: NonEmptyStr
    capabilities: tuple[NonEmptyStr, ...]
    status: ReadinessStatus
    content_hash: Sha256
    lineage: LineageRecord


class MemoryRuntimeView(StrictModel):
    artifact_name: Literal["memory_runtime_view"] = "memory_runtime_view"
    schema_id: Literal["memory_runtime_view.v1"] = "memory_runtime_view.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    artifact_id: NonEmptyStr
    access_policy_ref: ArtifactPointer
    memory_index_ref: ArtifactPointer
    memory_read_port_id: NonEmptyStr
    status: ReadinessStatus
    content_hash: Sha256
    lineage: LineageRecord


class ToolRuntimeView(StrictModel):
    artifact_name: Literal["tool_runtime_view"] = "tool_runtime_view"
    schema_id: Literal["tool_runtime_view.v1"] = "tool_runtime_view.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    artifact_id: NonEmptyStr
    tool_registry_ref: ArtifactPointer
    entitlement_ref: ArtifactPointer
    gateway_policy_ref: ArtifactPointer
    audit_contract_ref: ArtifactPointer
    gateway_port_id: NonEmptyStr
    status: ReadinessStatus
    content_hash: Sha256
    lineage: LineageRecord


class RuntimeFoundationContext(StrictModel):
    contract_pack_id: Literal["P3_INTEGRATION_CONTRACT_PACK_V2"] = CONTRACT_PACK_ID
    contract_pack_version: Literal["2.0.0"] = CONTRACT_PACK_VERSION
    identity: RunIdentity
    governance: FoundationGovernanceView
    population: PopulationRuntimeView
    social_graph: SocialGraphRuntimeView
    state: StateRuntimeView
    knowledge: KnowledgeRuntimeView
    memory: MemoryRuntimeView
    tooling: ToolRuntimeView
    status: ReadinessStatus
    degraded_capabilities: tuple[NonEmptyStr, ...] = ()
    blocking_reasons: tuple[NonEmptyStr, ...] = ()


class CycleKernelRequest(StrictModel):
    contract_pack_id: Literal["P3_INTEGRATION_CONTRACT_PACK_V2"] = CONTRACT_PACK_ID
    contract_pack_version: Literal["2.0.0"] = CONTRACT_PACK_VERSION
    request_id: NonEmptyStr
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    cycle_id: NonEmptyStr
    mode: CycleExecutionMode
    logical_time: datetime
    foundation_manifest_ref: ArtifactPointer
    prior_state_ref: ArtifactPointer
    stimulus_ref: ArtifactPointer
    schedule_context_ref: ArtifactPointer | None = None
    seed: int = Field(ge=0)
    capability_flags: CapabilityFlags
    budget: BudgetLimits

    @field_validator("logical_time")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("logical_time must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_mode_capabilities(self) -> "CycleKernelRequest":
        if self.mode is CycleExecutionMode.WARMUP_REPLAY:
            if self.capability_flags.emit_p4_outputs or self.capability_flags.emit_p9_outputs:
                raise ValueError("warm-up replay cannot emit P4 or P9 outputs")
            if self.capability_flags.allow_live_providers:
                raise ValueError("warm-up replay cannot use live providers")
        if self.mode is CycleExecutionMode.REPLAY and self.capability_flags.allow_live_providers:
            raise ValueError("replay cannot use live providers")
        if self.mode is CycleExecutionMode.DRY_RUN and (
            self.capability_flags.allow_live_providers or self.capability_flags.allow_tool_execution
        ):
            raise ValueError("dry run cannot execute providers or tools")
        return self


class CycleKernelResult(StrictModel):
    contract_pack_id: Literal["P3_INTEGRATION_CONTRACT_PACK_V2"] = CONTRACT_PACK_ID
    contract_pack_version: Literal["2.0.0"] = CONTRACT_PACK_VERSION
    request_id: NonEmptyStr
    cycle_id: NonEmptyStr
    status: CycleExecutionStatus
    closure_manifest_ref: ArtifactPointer
    next_state_ref: ArtifactPointer
    checkpoint_ref: ArtifactPointer
    audit_summary_ref: ArtifactPointer
    module_trace_ref: ArtifactPointer
    issues: tuple[NonEmptyStr, ...] = ()


class P3CycleClosureManifest(StrictModel):
    artifact_name: Literal["p3_cycle_closure_manifest"] = "p3_cycle_closure_manifest"
    schema_id: Literal["p3_cycle_closure_manifest.v1"] = "p3_cycle_closure_manifest.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    artifact_id: NonEmptyStr
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    cycle_id: NonEmptyStr
    completed_at: datetime
    foundation_manifest_ref: ArtifactPointer
    next_person_state_ref: ArtifactPointer
    next_belief_state_ref: ArtifactPointer
    next_memory_state_ref: ArtifactPointer
    next_social_graph_ref: ArtifactPointer
    next_endogenous_queue_ref: ArtifactPointer
    belief_commitments_ref: ArtifactPointer
    audit_summary_ref: ArtifactPointer
    available_from_cycle: NonEmptyStr
    status: ReadinessStatus
    content_hash: Sha256
    lineage: LineageRecord

    @field_validator("completed_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("completed_at must be timezone-aware")
        return value.astimezone(UTC)


class ReplayState(StrictModel):
    artifact_name: Literal["replay_state"] = "replay_state"
    schema_id: Literal["replay_state.v1"] = "replay_state.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    artifact_id: NonEmptyStr
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    source_cycle_id: NonEmptyStr
    available_from_cycle: NonEmptyStr
    as_of_time: datetime
    source: StateSource
    person_state_ref: ArtifactPointer
    belief_state_ref: ArtifactPointer
    memory_state_ref: ArtifactPointer
    social_graph_ref: ArtifactPointer
    pending_stimuli_ref: ArtifactPointer
    belief_commitments_ref: ArtifactPointer
    state_hash: Sha256
    lineage: LineageRecord

    @field_validator("as_of_time")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of_time must be timezone-aware")
        return value.astimezone(UTC)
