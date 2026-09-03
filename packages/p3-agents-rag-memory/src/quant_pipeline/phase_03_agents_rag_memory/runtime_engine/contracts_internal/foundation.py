from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .base import (
    ArtifactPointer,
    ExecutionStatus,
    LineageRecord,
    NonEmptyStr,
    NonNegativeInt,
    Probability,
    Sha256,
    StrictBoundaryModel,
    content_hash,
    utc,
)


class IdentityView(StrictBoundaryModel):
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    as_of_time: datetime

    @field_validator("as_of_time")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return utc(value)


class FoundationGovernanceView(IdentityView):
    schema_id: Literal["p3.integration.foundation_governance_view.v1"] = (
        "p3.integration.foundation_governance_view.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    pipeline_version: NonEmptyStr
    architecture_revision: NonEmptyStr
    pit_context: ArtifactPointer
    run_snapshot: ArtifactPointer
    model_cutoff_report: ArtifactPointer
    retro_policy_patch: ArtifactPointer
    belief_feedback_bundle: ArtifactPointer
    person_schema_policy: ArtifactPointer
    personality_tag_registry: ArtifactPointer
    status: ExecutionStatus


class PopulationPersonRecord(StrictBoundaryModel):
    person_id: NonEmptyStr
    economic_role: NonEmptyStr
    representation_weight: Annotated[float, Field(gt=0.0)]
    seed: NonNegativeInt
    availability_constraints: tuple[NonEmptyStr, ...] = ()
    capability_refs: tuple[NonEmptyStr, ...] = ()


class PopulationRuntimeView(IdentityView):
    schema_id: Literal["p3.integration.population_runtime_view.v1"] = (
        "p3.integration.population_runtime_view.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    population_hash: Sha256
    coverage_ratio: Probability
    formula_id: NonEmptyStr
    formula_version: NonEmptyStr
    population_manifest: ArtifactPointer
    social_graph: ArtifactPointer
    records: tuple[PopulationPersonRecord, ...]
    status: ExecutionStatus

    @model_validator(mode="after")
    def explicit_empty_status(self) -> "PopulationRuntimeView":
        if not self.records and self.status is ExecutionStatus.READY:
            raise ValueError("empty population must use EMPTY_VALID, DEGRADED, BLOCKED, or FAILED")
        return self


class StructuralFieldPolicy(StrictBoundaryModel):
    structural: tuple[NonEmptyStr, ...]
    slow_moving: tuple[NonEmptyStr, ...]
    dynamic: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def disjoint_sets(self) -> "StructuralFieldPolicy":
        groups = [set(self.structural), set(self.slow_moving), set(self.dynamic)]
        if groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2]:
            raise ValueError("field classifications must be disjoint")
        return self


class StateRuntimeView(IdentityView):
    schema_id: Literal["p3.integration.state_runtime_view.v1"] = (
        "p3.integration.state_runtime_view.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    current_person_state: ArtifactPointer
    current_belief_state: ArtifactPointer
    current_memory_state: ArtifactPointer
    current_social_graph: ArtifactPointer
    person_field_policy: StructuralFieldPolicy
    status: ExecutionStatus


class KnowledgeRuntimeView(IdentityView):
    schema_id: Literal["p3.integration.knowledge_runtime_view.v1"] = (
        "p3.integration.knowledge_runtime_view.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    rag_index: ArtifactPointer
    retrieval_manifest: ArtifactPointer
    graph_rag: ArtifactPointer
    graph_evidence: ArtifactPointer
    capabilities: tuple[NonEmptyStr, ...]
    status: ExecutionStatus


class MemoryRuntimeView(IdentityView):
    schema_id: Literal["p3.integration.memory_runtime_view.v1"] = (
        "p3.integration.memory_runtime_view.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    access_policy: ArtifactPointer
    memory_index: ArtifactPointer
    status: ExecutionStatus


class ToolRuntimeView(IdentityView):
    schema_id: Literal["p3.integration.tool_runtime_view.v1"] = (
        "p3.integration.tool_runtime_view.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    tool_registry: ArtifactPointer
    entitlement_panel: ArtifactPointer
    gateway_policy: ArtifactPointer
    audit_contract: ArtifactPointer
    status: ExecutionStatus


class FoundationRuntimeManifest(IdentityView):
    artifact_name: Literal["p3_foundation_runtime_manifest"] = "p3_foundation_runtime_manifest"
    schema_id: Literal["p3.integration.foundation_runtime_manifest.v1"] = (
        "p3.integration.foundation_runtime_manifest.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    artifact_id: NonEmptyStr
    pipeline_version: NonEmptyStr
    architecture_revision: NonEmptyStr
    lineage: LineageRecord
    governance_view: ArtifactPointer
    population_view: ArtifactPointer
    state_view: ArtifactPointer
    knowledge_view: ArtifactPointer
    memory_view: ArtifactPointer
    tool_view: ArtifactPointer
    prompt_bundle: ArtifactPointer
    model_registry: ArtifactPointer
    capabilities: tuple[NonEmptyStr, ...]
    status: ExecutionStatus
    degraded_capabilities: tuple[NonEmptyStr, ...] = ()
    blocking_reasons: tuple[NonEmptyStr, ...] = ()
    content_hash: Sha256

    @model_validator(mode="after")
    def manifest_consistent(self) -> "FoundationRuntimeManifest":
        if self.status is ExecutionStatus.READY and (
            self.degraded_capabilities or self.blocking_reasons
        ):
            raise ValueError("READY manifest cannot include degraded or blocking reasons")
        if self.status is ExecutionStatus.BLOCKED and not self.blocking_reasons:
            raise ValueError("BLOCKED manifest requires blocking reasons")
        payload = self.model_dump(mode="json", exclude={"content_hash"})
        if content_hash(payload) != self.content_hash:
            raise ValueError("foundation manifest content_hash is invalid")
        return self


class RuntimeFoundationContext(StrictBoundaryModel):
    """Materialized, validated foundation context consumed by S17-S24."""

    manifest: FoundationRuntimeManifest
    governance: FoundationGovernanceView
    population: PopulationRuntimeView
    state: StateRuntimeView
    knowledge: KnowledgeRuntimeView
    memory: MemoryRuntimeView
    tools: ToolRuntimeView
