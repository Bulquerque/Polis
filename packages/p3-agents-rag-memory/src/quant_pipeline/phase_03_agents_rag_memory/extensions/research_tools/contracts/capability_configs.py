"""Strict configuration contracts for P3.S34 capability and planning builders."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from ..core.models import NonEmptyStr, ResearchToolModel
from .configs import ManifestFileRecord, SchemaBundleEntry


class CapabilitySourceRule(ResearchToolModel):
    capability_id: NonEmptyStr
    source_capability_weights: dict[NonEmptyStr, Annotated[float, Field(ge=0.0, le=2.0)]] = Field(
        default_factory=dict
    )
    role_adjustments: dict[NonEmptyStr, Annotated[float, Field(ge=-1.0, le=1.0)]] = Field(
        default_factory=dict
    )
    institution_adjustments: dict[NonEmptyStr, Annotated[float, Field(ge=-1.0, le=1.0)]] = Field(
        default_factory=dict
    )
    resource_adjustments: dict[NonEmptyStr, Annotated[float, Field(ge=-1.0, le=1.0)]] = Field(
        default_factory=dict
    )
    constraint_adjustments: dict[NonEmptyStr, Annotated[float, Field(ge=-1.0, le=1.0)]] = Field(
        default_factory=dict
    )
    default_score: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0


class AccessClassRule(ResearchToolModel):
    capability_id: NonEmptyStr
    accepted_data_classes: tuple[NonEmptyStr, ...] = ()
    accepted_resource_labels: tuple[NonEmptyStr, ...] = ()
    accepted_institutions: tuple[NonEmptyStr, ...] = ()
    score_when_matched: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    default_score: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0


class ResourceResolutionRule(ResearchToolModel):
    resource_id: NonEmptyStr
    source_capability_keys: tuple[NonEmptyStr, ...] = ()
    accepted_resource_labels: tuple[NonEmptyStr, ...] = ()
    default_score: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    numeric_limit_by_label: dict[NonEmptyStr, Annotated[float, Field(ge=0.0)]] = Field(
        default_factory=dict
    )


class CapabilityProfilePolicyConfig(ResearchToolModel):
    schema_id: Literal["p3.research_tools.capability_profile_policy.v1"] = (
        "p3.research_tools.capability_profile_policy.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    policy_version: NonEmptyStr = "1.0.0"
    forbidden_source_fields: tuple[NonEmptyStr, ...]
    level_thresholds: dict[NonEmptyStr, Annotated[float, Field(ge=0.0, le=1.0)]]
    capability_rules: tuple[CapabilitySourceRule, ...]
    access_rules: tuple[AccessClassRule, ...]
    resource_rules: tuple[ResourceResolutionRule, ...]
    max_calls_per_cycle: Annotated[int, Field(ge=0, le=5)] = 5
    max_cost_units_per_cycle: Annotated[int, Field(ge=0, le=10_000)] = 100
    minimum_population_coverage: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0

    @model_validator(mode="after")
    def validate_thresholds(self) -> "CapabilityProfilePolicyConfig":
        required = {"NONE", "BASIC", "STANDARD", "ADVANCED", "SPECIALIST"}
        if set(self.level_thresholds) != required:
            raise ValueError("level_thresholds must define NONE, BASIC, STANDARD, ADVANCED, SPECIALIST")
        values = [self.level_thresholds[key] for key in ("NONE", "BASIC", "STANDARD", "ADVANCED", "SPECIALIST")]
        if values[0] != 0.0:
            raise ValueError("NONE threshold must be exactly zero")
        if any(left >= right for left, right in zip(values[:-1], values[1:], strict=True)):
            raise ValueError("level thresholds must be strictly increasing")
        groups = {
            "capability_rules": [item.capability_id for item in self.capability_rules],
            "access_rules": [item.capability_id for item in self.access_rules],
            "resource_rules": [item.resource_id for item in self.resource_rules],
        }
        for label, identifiers in groups.items():
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"{label} contains duplicate identifiers")
        if set(groups["capability_rules"]).intersection(groups["access_rules"]):
            raise ValueError("a capability cannot have both a source rule and an access rule")
        return self


class PlanNodeConfig(ResearchToolModel):
    node_id: NonEmptyStr
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    requested_mode: NonEmptyStr
    required: bool = True
    predecessors: tuple[NonEmptyStr, ...] = ()
    stop_conditions: tuple[NonEmptyStr, ...] = ()
    downgrade_policy: Literal["ALLOW", "BLOCK", "SKIP_OPTIONAL"] = "ALLOW"
    visible_call_cost: Annotated[int, Field(ge=0, le=5)] = 1
    priority: Annotated[int, Field(ge=0, le=10_000)] = 100


class ResearchPlanConfig(ResearchToolModel):
    plan_id: NonEmptyStr
    title: NonEmptyStr
    description: NonEmptyStr
    subject_kinds: tuple[NonEmptyStr, ...]
    nodes: tuple[PlanNodeConfig, ...]
    continuation_allowed: bool = True
    maximum_visible_calls_per_cycle: Annotated[int, Field(ge=0, le=5)] = 5


class ResearchPlanRegistryConfig(ResearchToolModel):
    schema_id: Literal["p3.research_tools.plan_registry_config.v1"] = (
        "p3.research_tools.plan_registry_config.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    registry_version: NonEmptyStr = "1.0.0"
    plans: tuple[ResearchPlanConfig, ...]


class ResearchEntitlementPolicyConfig(ResearchToolModel):
    schema_id: Literal["p3.research_tools.entitlement_policy.v1"] = (
        "p3.research_tools.entitlement_policy.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    policy_version: NonEmptyStr = "1.0.0"
    default_decision: Literal["DENY"] = "DENY"
    deny_overrides: Literal[True] = True
    preserve_applicable_legacy_denies: Literal[True] = True
    maximum_calls_per_cycle: Annotated[int, Field(ge=0, le=5)] = 5
    minimum_score_by_band: dict[Literal["1", "2", "3", "4"], Annotated[float, Field(ge=0.0, le=1.0)]]
    required_resource_scores_by_band: dict[Literal["1", "2", "3", "4"], dict[NonEmptyStr, Annotated[float, Field(ge=0.0, le=1.0)]]]
    required_access_capability_ids: tuple[NonEmptyStr, ...] = ("public_data_access",)
    allowed_provider_availability: tuple[NonEmptyStr, ...] = ("QUALIFIED_LOCAL",)
    blocked_view_statuses: tuple[NonEmptyStr, ...] = ("BLOCKED_UPSTREAM", "FAILED")
    internal_provider_id: NonEmptyStr = "internal_research"
    credential_policy: Literal["HANDLE_ONLY"] = "HANDLE_ONLY"
    forbidden_constraints: tuple[NonEmptyStr, ...] = ("no_external_data",)


class ContextToolDescriptorPolicyConfig(ResearchToolModel):
    schema_id: Literal["p3.research_tools.context_descriptor_policy.v1"] = (
        "p3.research_tools.context_descriptor_policy.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    policy_version: NonEmptyStr = "1.0.0"
    tokenizer_mode: Literal["DETERMINISTIC_REGEX"] = "DETERMINISTIC_REGEX"
    section_header: NonEmptyStr = "AUTHORIZED_RESEARCH_TOOLS"
    max_descriptor_tokens: Annotated[int, Field(ge=0, le=16_384)] = 1_500
    max_operations_per_tool: Annotated[int, Field(ge=1, le=64)] = 12
    include_examples: bool = True
    max_example_characters: Annotated[int, Field(ge=0, le=1_000)] = 180
    preserve_section_types: tuple[NonEmptyStr, ...] = (
        "PERSON_IDENTITY",
        "PRIOR_BELIEFS",
        "RETRIEVED_EVIDENCE",
    )
    mandatory_instructions: tuple[NonEmptyStr, ...]
    operation_examples: dict[NonEmptyStr, dict[str, JsonValue]] = Field(default_factory=dict)


class S34SchemaBundleManifest(ResearchToolModel):
    schema_id: Literal["p3.research_tools.s34_schema_bundle_manifest.v1"] = (
        "p3.research_tools.s34_schema_bundle_manifest.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    entries: tuple[SchemaBundleEntry, ...]


class S34ConfigManifest(ResearchToolModel):
    schema_id: Literal["p3.research_tools.s34_config_manifest.v1"] = (
        "p3.research_tools.s34_config_manifest.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    files: tuple[ManifestFileRecord, ...]
