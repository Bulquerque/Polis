"""Public deterministic facade for the five P3.S34 modules."""

from __future__ import annotations

from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    CognitionConfig,
    PersonToolEntitlementPanel as S21PersonToolEntitlementPanel,
)

from .compatibility.s20_context import build_context_overlay
from .compatibility.s21_entitlements import build_entitlement_overlay
from .compatibility.s21_gateway_policy import project_gateway_policy
from .contracts.artifacts import (
    CanonicalResearchToolCatalog,
    CanonicalToolOperationRegistry,
    ProviderTransportOverlay,
    ResearchModeRegistry,
)
from .contracts.boundary_artifacts import Phase2ResearchViewReadinessReport
from .contracts.capability_artifacts import (
    PersonResearchCapabilityPanel,
    PersonResearchResourcePanel,
    ResearchCapabilityTaxonomy,
    ResearchPlanRegistry,
)
from .contracts.capability_configs import (
    CapabilityProfilePolicyConfig,
    ContextToolDescriptorPolicyConfig,
    ResearchEntitlementPolicyConfig,
    ResearchPlanRegistryConfig,
)
from .contracts.configs import ResearchCapabilityTaxonomyConfig
from .core.errors import fail
from .services.capability_taxonomy import build_capability_taxonomy
from .services.person_capabilities import build_person_capability_profiles
from .services.research_plans import build_research_plan_registry


def build_capability_taxonomy_contracts(inputs: dict[str, Any]) -> dict[str, Any]:
    taxonomy, matrix = build_capability_taxonomy(
        taxonomy_config=ResearchCapabilityTaxonomyConfig.model_validate(
            inputs["research_capability_taxonomy_config"], strict=False
        ),
        tool_catalog=CanonicalResearchToolCatalog.model_validate(
            inputs["canonical_research_tool_catalog"], strict=False
        ),
        operation_registry=CanonicalToolOperationRegistry.model_validate(
            inputs["canonical_tool_operation_registry"], strict=False
        ),
        mode_registry=ResearchModeRegistry.model_validate(
            inputs["research_mode_registry"], strict=False
        ),
        person_schema_policy=inputs["person_schema_policy"],
    )
    return {
        "research_capability_taxonomy": taxonomy.model_dump(mode="json"),
        "capability_operation_requirement_matrix": matrix.model_dump(mode="json"),
    }


def build_person_research_profiles(inputs: dict[str, Any]) -> dict[str, Any]:
    capabilities, resources, coverage = build_person_capability_profiles(
        person_seed_panel=inputs["person_seed_panel"],
        validated_population_manifest=inputs["validated_population_manifest"],
        person_schema_policy=inputs["person_schema_policy"],
        taxonomy=ResearchCapabilityTaxonomy.model_validate(
            inputs["research_capability_taxonomy"], strict=False
        ),
        policy=CapabilityProfilePolicyConfig.model_validate(
            inputs["capability_profile_policy_config"], strict=False
        ),
        phase3_run_snapshot=inputs["phase3_run_snapshot"],
    )
    return {
        "person_research_capability_panel": capabilities.model_dump(mode="json"),
        "person_research_resource_panel": resources.model_dump(mode="json"),
        "capability_profile_coverage_report": coverage.model_dump(mode="json"),
    }


def build_research_plan_templates(inputs: dict[str, Any]) -> dict[str, Any]:
    registry, matrix, readiness = build_research_plan_registry(
        config=ResearchPlanRegistryConfig.model_validate(
            inputs["research_plan_registry_config"], strict=False
        ),
        operation_registry=CanonicalToolOperationRegistry.model_validate(
            inputs["canonical_tool_operation_registry"], strict=False
        ),
        mode_registry=ResearchModeRegistry.model_validate(
            inputs["research_mode_registry"], strict=False
        ),
        taxonomy=ResearchCapabilityTaxonomy.model_validate(
            inputs["research_capability_taxonomy"], strict=False
        ),
        view_readiness=Phase2ResearchViewReadinessReport.model_validate(
            inputs["phase2_research_view_readiness_report"], strict=False
        ),
    )
    return {
        "research_plan_registry": registry.model_dump(mode="json"),
        "research_plan_dependency_matrix": matrix.model_dump(mode="json"),
        "research_plan_readiness_report": readiness.model_dump(mode="json"),
    }


def build_effective_entitlements(inputs: dict[str, Any]) -> dict[str, Any]:
    panel, audit = build_entitlement_overlay(
        legacy_entitlement_panel=inputs["person_tool_entitlement_panel"],
        capability_panel=PersonResearchCapabilityPanel.model_validate(
            inputs["person_research_capability_panel"], strict=False
        ),
        resource_panel=PersonResearchResourcePanel.model_validate(
            inputs["person_research_resource_panel"], strict=False
        ),
        operation_registry=CanonicalToolOperationRegistry.model_validate(
            inputs["canonical_tool_operation_registry"], strict=False
        ),
        mode_registry=ResearchModeRegistry.model_validate(
            inputs["research_mode_registry"], strict=False
        ),
        plan_registry=ResearchPlanRegistry.model_validate(
            inputs["research_plan_registry"], strict=False
        ),
        view_readiness=Phase2ResearchViewReadinessReport.model_validate(
            inputs["phase2_research_view_readiness_report"], strict=False
        ),
        provider_overlay=ProviderTransportOverlay.model_validate(
            inputs["provider_transport_overlay"], strict=False
        ),
        policy=ResearchEntitlementPolicyConfig.model_validate(
            inputs["research_entitlement_policy_config"], strict=False
        ),
        gateway_policy=project_gateway_policy(inputs["mcp_gateway_policy"]),
        phase3_run_snapshot=inputs["phase3_run_snapshot"],
    )
    return {
        "extended_person_tool_entitlement_panel": panel.model_dump(mode="json"),
        "entitlement_resolution_audit": audit.model_dump(mode="json"),
    }


def build_context_tool_overlay(inputs: dict[str, Any]) -> dict[str, Any]:
    bundle, audit = build_context_overlay(
        validated_person_context_bundle=inputs["validated_person_context_bundle"],
        entitlement_panel=S21PersonToolEntitlementPanel.model_validate(
            inputs["extended_person_tool_entitlement_panel"], strict=False
        ),
        capability_panel=PersonResearchCapabilityPanel.model_validate(
            inputs["person_research_capability_panel"], strict=False
        ),
        plan_registry=ResearchPlanRegistry.model_validate(
            inputs["research_plan_registry"], strict=False
        ),
        tool_catalog=CanonicalResearchToolCatalog.model_validate(
            inputs["canonical_research_tool_catalog"], strict=False
        ),
        operation_registry=CanonicalToolOperationRegistry.model_validate(
            inputs["canonical_tool_operation_registry"], strict=False
        ),
        mode_registry=ResearchModeRegistry.model_validate(
            inputs["research_mode_registry"], strict=False
        ),
        person_seed_panel=inputs["person_seed_panel"],
        phase3_run_snapshot=inputs["phase3_run_snapshot"],
        cognition_config=CognitionConfig.model_validate(inputs["cognition_config"], strict=False),
        descriptor_policy=ContextToolDescriptorPolicyConfig.model_validate(
            inputs["context_tool_descriptor_policy_config"], strict=False
        ),
    )
    return {
        "extended_validated_person_context_bundle": bundle.model_dump(mode="json"),
        "context_projection_audit": audit.model_dump(mode="json"),
    }
