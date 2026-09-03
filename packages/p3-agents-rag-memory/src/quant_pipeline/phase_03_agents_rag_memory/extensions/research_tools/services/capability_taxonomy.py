"""Deterministic capability taxonomy builder for P3.S34.M01."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from ..contracts.artifacts import (
    ArtifactStatus,
    CanonicalResearchToolCatalog,
    CanonicalToolOperationRegistry,
    ResearchModeRegistry,
)
from ..contracts.capability_artifacts import (
    CapabilityCategory,
    CapabilityDefinitionRecord,
    CapabilityOperationRequirementMatrix,
    CapabilityOperationRequirementRecord,
    ResearchCapabilityTaxonomy,
)
from ..contracts.configs import ResearchCapabilityTaxonomyConfig
from ..core.errors import fail
from .artifact_construction import finalize, lineage


def _policy_mapping(value: object) -> Mapping[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    if not isinstance(value, Mapping):
        raise fail("P3RT-CONTRACT-3401", "person_schema_policy must be a mapping")
    return value


def build_capability_taxonomy(
    *,
    taxonomy_config: ResearchCapabilityTaxonomyConfig,
    tool_catalog: CanonicalResearchToolCatalog,
    operation_registry: CanonicalToolOperationRegistry,
    mode_registry: ResearchModeRegistry,
    person_schema_policy: object,
) -> tuple[ResearchCapabilityTaxonomy, CapabilityOperationRequirementMatrix]:
    definitions: dict[str, CapabilityDefinitionRecord] = {}
    for item in taxonomy_config.capabilities:
        if item.capability_id in definitions:
            raise fail(
                "P3RT-CONTRACT-3402",
                "capability taxonomy contains a duplicate capability_id",
                {"capability_id": item.capability_id},
            )
        definitions[item.capability_id] = CapabilityDefinitionRecord(
            capability_id=item.capability_id,
            category=CapabilityCategory(item.category),
            description=item.description,
        )

    policy = _policy_mapping(person_schema_policy)
    forbidden = {str(value) for value in policy.get("forbidden_entitlement_attributes", ())}
    overlap = sorted(forbidden & set(definitions))
    if overlap:
        raise fail(
            "P3RT-CONTRACT-3403",
            "forbidden entitlement attributes cannot be capability IDs",
            {"capability_ids": overlap},
        )

    operation_keys = {(item.tool_id, item.operation_id) for item in operation_registry.operations}
    tool_ids = {item.tool_id for item in tool_catalog.tools}
    requirements: list[CapabilityOperationRequirementRecord] = []
    for mode in mode_registry.modes:
        key = (mode.tool_id, mode.operation_id)
        if key not in operation_keys or mode.tool_id not in tool_ids:
            raise fail(
                "P3RT-CONTRACT-3404",
                "mode references an unknown canonical operation",
                {"tool_id": mode.tool_id, "operation_id": mode.operation_id, "mode_id": mode.mode_id},
            )
        for capability_id in mode.required_capabilities:
            definition = definitions.get(capability_id)
            if definition is None:
                raise fail(
                    "P3RT-CONTRACT-3405",
                    "mode references an unknown capability",
                    {"capability_id": capability_id, "mode_id": mode.mode_id},
                )
            if definition.category is not CapabilityCategory.DOMAIN:
                raise fail(
                    "P3RT-CONTRACT-3406",
                    "required_capabilities must reference DOMAIN capabilities",
                    {"capability_id": capability_id, "category": definition.category.value},
                )
        for method_id in mode.required_methods:
            definition = definitions.get(method_id)
            if definition is None:
                raise fail(
                    "P3RT-CONTRACT-3407",
                    "mode references an unknown method",
                    {"method_id": method_id, "mode_id": mode.mode_id},
                )
            if definition.category is not CapabilityCategory.METHOD:
                raise fail(
                    "P3RT-CONTRACT-3408",
                    "required_methods must reference METHOD capabilities",
                    {"method_id": method_id, "category": definition.category.value},
                )
        requirements.append(
            CapabilityOperationRequirementRecord(
                tool_id=mode.tool_id,
                operation_id=mode.operation_id,
                mode_id=mode.mode_id,
                band=mode.band,
                required_capability_ids=tuple(sorted(mode.required_capabilities)),
                required_method_ids=tuple(sorted(mode.required_methods)),
                required_access_ids=(),
                required_resource_ids=(),
            )
        )

    source_inputs = (taxonomy_config, tool_catalog, operation_registry, mode_registry, policy)
    counts = Counter(item.category for item in definitions.values())
    taxonomy = finalize(
        ResearchCapabilityTaxonomy,
        {
            "status": ArtifactStatus.READY,
            "lineage": lineage("P3.S34.M01", tool_catalog.contract_version, source_inputs),
            "capabilities": tuple(sorted(definitions.values(), key=lambda item: item.capability_id)),
            "category_counts": {category: counts.get(category, 0) for category in CapabilityCategory},
        },
    )
    matrix = finalize(
        CapabilityOperationRequirementMatrix,
        {
            "status": ArtifactStatus.READY,
            "lineage": lineage("P3.S34.M01", tool_catalog.contract_version, source_inputs),
            "records": tuple(
                sorted(requirements, key=lambda item: (item.tool_id, item.operation_id, item.band, item.mode_id))
            ),
        },
    )
    return taxonomy, matrix
