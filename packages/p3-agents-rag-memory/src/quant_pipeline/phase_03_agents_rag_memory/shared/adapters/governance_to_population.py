from __future__ import annotations

from typing import Any, Mapping

from quant_pipeline.phase_03_agents_rag_memory.foundation.population.s5.models import (
    PersonSchemaPolicy,
    PersonalityTagRegistry,
)
from quant_pipeline.phase_03_agents_rag_memory.shared.contracts import model_or_mapping


class GovernancePopulationCompatibilityError(ValueError):
    """Raised when the operational population view is not a valid projection of governance authority."""


def to_population_tag_registry(
    registry: Mapping[str, Any],
) -> PersonalityTagRegistry:
    """Project the rich governance tag authority into the bounded population-generation view."""

    source = model_or_mapping(registry)
    categories: list[dict[str, object]] = []
    for category in source.get("categories", []):
        active = [
            {"tag_id": tag["tag_id"], "description": tag["description"]}
            for tag in category.get("tags", [])
            if tag.get("status", "ACTIVE") == "ACTIVE"
        ]
        if active:
            categories.append({"category_id": category["category_id"], "tags": tuple(active)})
    if not categories:
        raise GovernancePopulationCompatibilityError("governance tag registry has no active tags")
    assignment_contract = source.get("assignment_contract", {})
    required = ("intensity", "confidence")
    if any(name not in assignment_contract for name in required):
        raise GovernancePopulationCompatibilityError("governance assignment contract must define intensity and confidence")
    payload = {
        "registry_id": source["registry_id"],
        "policy": source["policy"],
        "assignment_fields": tuple(required),
        "categories": tuple(categories),
        "schema_version": source.get("schema_version", "2.0.0"),
    }
    return PersonalityTagRegistry.model_validate(payload, strict=True)


def to_population_person_policy(
    person_policy: Mapping[str, Any],
    tag_registry: Mapping[str, Any],
    operational_policy: Mapping[str, Any],
    objective_aliases: Mapping[str, Mapping[str, str]],
) -> PersonSchemaPolicy:
    """Create the internal population-generation policy while preserving governance as semantic authority.

    Experience/education constraints are operational generation rules, not a second person ontology.
    The function fails when a role, family, tag or objective alias is not backed by governance.
    """

    authority = model_or_mapping(person_policy)
    tags = to_population_tag_registry(tag_registry)
    operation = model_or_mapping(operational_policy)
    role_to_family = authority["role_taxonomy"]["role_to_family"]
    canonical_objectives = set(authority["objective_registry"]["dimensions"])
    canonical_tags = tags.tag_ids()

    operation_tags = tuple(operation["allowed_tag_ids"])
    unknown_tags = sorted(set(operation_tags) - canonical_tags)
    if unknown_tags:
        raise GovernancePopulationCompatibilityError(f"Operational policy uses unknown governance tags: {unknown_tags}")

    roles: list[dict[str, object]] = []
    for role in operation["roles"]:
        role_id = role["role_id"]
        expected_family = role_to_family.get(role_id)
        if expected_family is None:
            raise GovernancePopulationCompatibilityError(f"Operational role is absent from governance authority: {role_id}")
        if expected_family != role["role_family"]:
            raise GovernancePopulationCompatibilityError(
                f"Role family mismatch for {role_id}: {role['role_family']} != {expected_family}"
            )
        for objective in role["allowed_objectives"]:
            if objective in canonical_objectives:
                continue
            mapped = objective_aliases.get(objective, {}).get(expected_family)
            if mapped not in canonical_objectives:
                raise GovernancePopulationCompatibilityError(
                    f"Objective {objective!r} for family {expected_family!r} has no valid governance mapping"
                )
        role_payload = dict(role)
        role_payload["allowed_objectives"] = tuple(role_payload["allowed_objectives"])
        role_payload["allowed_occupation_families"] = tuple(role_payload["allowed_occupation_families"])
        role_payload["required_resource_flags"] = tuple(role_payload.get("required_resource_flags", ()))
        roles.append(role_payload)

    payload = {
        "schema_id": "person_schema_policy.v2",
        "schema_version": "2.0.0-population-view",
        "personality_tag_registry_id": tags.registry_id,
        "allowed_tag_ids": tuple(operation_tags),
        "roles": tuple(roles),
        "objective_dimensions": tuple(operation["objective_dimensions"]),
        "experience_bands": tuple(operation["experience_bands"]),
        "education_rank": operation["education_rank"],
        "capability_minimum_education_rank": operation.get("capability_minimum_education_rank", {}),
        "objective_sum_tolerance": operation.get("objective_sum_tolerance", 1e-9),
    }
    return PersonSchemaPolicy.model_validate(payload, strict=True)
