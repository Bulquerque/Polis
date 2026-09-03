"""Canonical serialized artifacts produced by P3.S34."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from ..core.models import NonEmptyStr, ResearchToolModel
from .artifacts import ArtifactEnvelope


class CapabilityCategory(StrEnum):
    DOMAIN = "DOMAIN"
    METHOD = "METHOD"
    ACCESS = "ACCESS"
    RESOURCE = "RESOURCE"


class CapabilityLevel(StrEnum):
    NONE = "NONE"
    BASIC = "BASIC"
    STANDARD = "STANDARD"
    ADVANCED = "ADVANCED"
    SPECIALIST = "SPECIALIST"


class ReadinessStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


class DecisionStatus(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class CapabilityDefinitionRecord(ResearchToolModel):
    capability_id: NonEmptyStr
    category: CapabilityCategory
    description: NonEmptyStr


class ResearchCapabilityTaxonomy(ArtifactEnvelope):
    artifact_name: Literal["research_capability_taxonomy"] = "research_capability_taxonomy"
    schema_id: Literal["p3.research_tools.capability_taxonomy.v1"] = (
        "p3.research_tools.capability_taxonomy.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    capabilities: tuple[CapabilityDefinitionRecord, ...]
    category_counts: dict[CapabilityCategory, Annotated[int, Field(ge=0)]]


class CapabilityOperationRequirementRecord(ResearchToolModel):
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    mode_id: NonEmptyStr
    band: Literal[1, 2, 3, 4]
    required_capability_ids: tuple[NonEmptyStr, ...] = ()
    required_method_ids: tuple[NonEmptyStr, ...] = ()
    required_access_ids: tuple[NonEmptyStr, ...] = ()
    required_resource_ids: tuple[NonEmptyStr, ...] = ()


class CapabilityOperationRequirementMatrix(ArtifactEnvelope):
    artifact_name: Literal["capability_operation_requirement_matrix"] = (
        "capability_operation_requirement_matrix"
    )
    schema_id: Literal["p3.research_tools.capability_requirement_matrix.v1"] = (
        "p3.research_tools.capability_requirement_matrix.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    records: tuple[CapabilityOperationRequirementRecord, ...]


class ScoreComponent(ResearchToolModel):
    component_id: NonEmptyStr
    source: NonEmptyStr
    source_value: float | str | bool | None = None
    adjustment: Annotated[float, Field(ge=-1.0, le=1.0)]
    explanation: NonEmptyStr


class PersonCapabilityRecord(ResearchToolModel):
    person_id: NonEmptyStr
    capability_id: NonEmptyStr
    category: CapabilityCategory
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    level: CapabilityLevel
    components: tuple[ScoreComponent, ...]
    policy_version: NonEmptyStr


class PersonResearchCapabilityPanel(ArtifactEnvelope):
    artifact_name: Literal["person_research_capability_panel"] = "person_research_capability_panel"
    schema_id: Literal["p3.research_tools.person_capabilities.v1"] = (
        "p3.research_tools.person_capabilities.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    records: tuple[PersonCapabilityRecord, ...]
    person_count: Annotated[int, Field(ge=0)]
    capability_count: Annotated[int, Field(ge=0)]


class PersonResourceRecord(ResearchToolModel):
    person_id: NonEmptyStr
    resource_id: NonEmptyStr
    normalized_score: Annotated[float, Field(ge=0.0, le=1.0)]
    numeric_limit: Annotated[float, Field(ge=0.0)] | None = None
    source_labels: tuple[NonEmptyStr, ...] = ()
    policy_version: NonEmptyStr


class PersonResearchResourcePanel(ArtifactEnvelope):
    artifact_name: Literal["person_research_resource_panel"] = "person_research_resource_panel"
    schema_id: Literal["p3.research_tools.person_resources.v1"] = (
        "p3.research_tools.person_resources.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    records: tuple[PersonResourceRecord, ...]


class CapabilityProfileCoverageReport(ArtifactEnvelope):
    artifact_name: Literal["capability_profile_coverage_report"] = (
        "capability_profile_coverage_report"
    )
    schema_id: Literal["p3.research_tools.capability_profile_coverage.v1"] = (
        "p3.research_tools.capability_profile_coverage.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    expected_person_count: Annotated[int, Field(ge=0)]
    profiled_person_count: Annotated[int, Field(ge=0)]
    coverage_ratio: Annotated[float, Field(ge=0.0, le=1.0)]
    missing_person_ids: tuple[NonEmptyStr, ...] = ()
    forbidden_source_fields_detected: tuple[NonEmptyStr, ...] = ()
    issues: tuple[NonEmptyStr, ...] = ()


class ResearchPlanNode(ResearchToolModel):
    node_id: NonEmptyStr
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    requested_mode: NonEmptyStr
    required: bool
    predecessors: tuple[NonEmptyStr, ...]
    stop_conditions: tuple[NonEmptyStr, ...]
    downgrade_policy: NonEmptyStr
    visible_call_cost: Annotated[int, Field(ge=0, le=5)]
    priority: Annotated[int, Field(ge=0, le=10_000)]


class ResearchPlanTemplate(ResearchToolModel):
    plan_id: NonEmptyStr
    title: NonEmptyStr
    description: NonEmptyStr
    subject_kinds: tuple[NonEmptyStr, ...]
    nodes: tuple[ResearchPlanNode, ...]
    continuation_allowed: bool
    maximum_visible_calls_per_cycle: Annotated[int, Field(ge=0, le=5)]


class ResearchPlanRegistry(ArtifactEnvelope):
    artifact_name: Literal["research_plan_registry"] = "research_plan_registry"
    schema_id: Literal["p3.research_tools.plan_registry.v1"] = "p3.research_tools.plan_registry.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    registry_version: NonEmptyStr
    plans: tuple[ResearchPlanTemplate, ...]


class ResearchPlanDependencyRecord(ResearchToolModel):
    plan_id: NonEmptyStr
    node_id: NonEmptyStr
    predecessor_ids: tuple[NonEmptyStr, ...]
    topological_index: Annotated[int, Field(ge=0)]


class ResearchPlanDependencyMatrix(ArtifactEnvelope):
    artifact_name: Literal["research_plan_dependency_matrix"] = "research_plan_dependency_matrix"
    schema_id: Literal["p3.research_tools.plan_dependency_matrix.v1"] = (
        "p3.research_tools.plan_dependency_matrix.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    records: tuple[ResearchPlanDependencyRecord, ...]


class ResearchPlanReadinessRecord(ResearchToolModel):
    plan_id: NonEmptyStr
    node_id: NonEmptyStr
    status: ReadinessStatus
    available_mode_id: NonEmptyStr | None = None
    missing_view_classes: tuple[NonEmptyStr, ...] = ()
    reason_codes: tuple[NonEmptyStr, ...] = ()


class ResearchPlanReadinessReport(ArtifactEnvelope):
    artifact_name: Literal["research_plan_readiness_report"] = "research_plan_readiness_report"
    schema_id: Literal["p3.research_tools.plan_readiness.v1"] = "p3.research_tools.plan_readiness.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    records: tuple[ResearchPlanReadinessRecord, ...]
    ready_plan_ids: tuple[NonEmptyStr, ...]
    degraded_plan_ids: tuple[NonEmptyStr, ...]
    blocked_plan_ids: tuple[NonEmptyStr, ...]


class EntitlementOperationDecision(ResearchToolModel):
    person_id: NonEmptyStr
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    decision: DecisionStatus
    allowed_mode_ids: tuple[NonEmptyStr, ...] = ()
    provider_id: NonEmptyStr | None = None
    budget_calls_per_cycle: Annotated[int, Field(ge=0, le=5)]
    reason_codes: tuple[NonEmptyStr, ...]


class EntitlementResolutionAudit(ArtifactEnvelope):
    artifact_name: Literal["entitlement_resolution_audit"] = "entitlement_resolution_audit"
    schema_id: Literal["p3.research_tools.entitlement_audit.v1"] = (
        "p3.research_tools.entitlement_audit.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    decisions: tuple[EntitlementOperationDecision, ...]
    allowed_decision_count: Annotated[int, Field(ge=0)]
    denied_decision_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def counts_match(self) -> "EntitlementResolutionAudit":
        allowed = sum(item.decision is DecisionStatus.ALLOW for item in self.decisions)
        denied = sum(item.decision is DecisionStatus.DENY for item in self.decisions)
        if self.allowed_decision_count != allowed or self.denied_decision_count != denied:
            raise ValueError("entitlement audit counts do not match decisions")
        return self


class ContextDescriptorRecord(ResearchToolModel):
    person_id: NonEmptyStr
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    mode_ids: tuple[NonEmptyStr, ...]
    descriptor_text: NonEmptyStr
    estimated_tokens: Annotated[int, Field(ge=0)]
    included: bool
    reason_codes: tuple[NonEmptyStr, ...] = ()


class ContextProjectionRecord(ResearchToolModel):
    person_id: NonEmptyStr
    source_context_id: NonEmptyStr
    activation_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    source_token_count: Annotated[int, Field(ge=0)]
    descriptor_token_count: Annotated[int, Field(ge=0)]
    final_token_count: Annotated[int, Field(ge=0)]
    context_token_limit: Annotated[int, Field(gt=0)]
    allowed_tool_ids: tuple[NonEmptyStr, ...]
    omitted_operation_refs: tuple[NonEmptyStr, ...]
    warnings: tuple[NonEmptyStr, ...] = ()


class ContextProjectionAudit(ArtifactEnvelope):
    artifact_name: Literal["context_projection_audit"] = "context_projection_audit"
    schema_id: Literal["p3.research_tools.context_projection_audit.v1"] = (
        "p3.research_tools.context_projection_audit.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    records: tuple[ContextProjectionRecord, ...]
    descriptors: tuple[ContextDescriptorRecord, ...]
    source_bundle_hash: NonEmptyStr
    consumer_schema_version: Literal["p3.s21.v1"] = "p3.s21.v1"
