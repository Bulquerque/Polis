"""Public deterministic facade for the four P3.S32 modules."""

from __future__ import annotations

from typing import Any

from .contracts.artifacts import (
    CanonicalResearchToolCatalog,
    CanonicalToolOperationRegistry,
    CompatibilityAliasRegistry,
    ExtendedToolRegistryOverlay,
    LegacyContractProjectionReport,
    OperationModeMatrix,
    ProviderTransportOverlay,
    ResearchModeRegistry,
    ResearchToolContractPackManifest,
    ResearchToolExtensionSnapshot,
)
from .contracts.configs import (
    CompatibilityAliasConfig,
    ExtensionConfigManifest,
    OperationModeRegistryConfig,
    PromptDescriptorTemplateManifest,
    ProviderTransportBindingsConfig,
    ResearchCapabilityTaxonomyConfig,
    ResearchToolCatalogConfig,
    SchemaBundleManifest,
)
from .services import build_catalog, build_compatibility, build_modes, build_snapshot


def build_canonical_catalog(inputs: dict[str, Any]) -> dict[str, Any]:
    catalog, registry = build_catalog(
        catalog_config=ResearchToolCatalogConfig.model_validate(inputs["research_tool_catalog_config"], strict=False),
        provider_bindings=ProviderTransportBindingsConfig.model_validate(
            inputs["provider_transport_bindings_config"], strict=False
        ),
        schema_manifest=SchemaBundleManifest.model_validate(inputs["schema_bundle_manifest"], strict=False),
        contract_version=str(inputs["extension_contract_version"]),
    )
    return {
        "canonical_research_tool_catalog": catalog.model_dump(mode="json"),
        "canonical_tool_operation_registry": registry.model_dump(mode="json"),
    }


def build_mode_registry(inputs: dict[str, Any]) -> dict[str, Any]:
    registry, matrix = build_modes(
        operation_registry=CanonicalToolOperationRegistry.model_validate(
            inputs["canonical_tool_operation_registry"], strict=False
        ),
        mode_config=OperationModeRegistryConfig.model_validate(
            inputs["operation_mode_registry_config"], strict=False
        ),
        capability_taxonomy=ResearchCapabilityTaxonomyConfig.model_validate(
            inputs["research_capability_taxonomy_config"], strict=False
        ),
    )
    return {
        "research_mode_registry": registry.model_dump(mode="json"),
        "operation_mode_matrix": matrix.model_dump(mode="json"),
    }


def build_compatibility_overlay(inputs: dict[str, Any]) -> dict[str, Any]:
    overlay, providers, aliases, report = build_compatibility(
        legacy_tool_registry=inputs["tool_registry"],
        legacy_gateway_policy=inputs["mcp_gateway_policy"],
        legacy_provider_registry=inputs["provider_adapter_registry_config"],
        catalog=CanonicalResearchToolCatalog.model_validate(
            inputs["canonical_research_tool_catalog"], strict=False
        ),
        operation_registry=CanonicalToolOperationRegistry.model_validate(
            inputs["canonical_tool_operation_registry"], strict=False
        ),
        alias_config=CompatibilityAliasConfig.model_validate(
            inputs["compatibility_alias_config"], strict=False
        ),
    )
    return {
        "extended_tool_registry_overlay": overlay.model_dump(mode="json"),
        "provider_transport_overlay": providers.model_dump(mode="json"),
        "compatibility_alias_registry": aliases.model_dump(mode="json"),
        "legacy_contract_projection_report": report.model_dump(mode="json"),
    }


def build_extension_snapshot(inputs: dict[str, Any]) -> dict[str, Any]:
    snapshot, manifest = build_snapshot(
        catalog=CanonicalResearchToolCatalog.model_validate(
            inputs["canonical_research_tool_catalog"], strict=False
        ),
        operation_registry=CanonicalToolOperationRegistry.model_validate(
            inputs["canonical_tool_operation_registry"], strict=False
        ),
        mode_registry=ResearchModeRegistry.model_validate(inputs["research_mode_registry"], strict=False),
        operation_mode_matrix=OperationModeMatrix.model_validate(inputs["operation_mode_matrix"], strict=False),
        provider_overlay=ProviderTransportOverlay.model_validate(
            inputs["provider_transport_overlay"], strict=False
        ),
        alias_registry=CompatibilityAliasRegistry.model_validate(
            inputs["compatibility_alias_registry"], strict=False
        ),
        schema_manifest=SchemaBundleManifest.model_validate(inputs["schema_bundle_manifest"], strict=False),
        prompt_manifest=PromptDescriptorTemplateManifest.model_validate(
            inputs["prompt_descriptor_template_manifest"], strict=False
        ),
        config_manifest=ExtensionConfigManifest.model_validate(
            inputs["extension_config_manifest"], strict=False
        ),
    )
    return {
        "research_tool_extension_snapshot": snapshot.model_dump(mode="json"),
        "research_tool_contract_pack_manifest": manifest.model_dump(mode="json"),
    }
