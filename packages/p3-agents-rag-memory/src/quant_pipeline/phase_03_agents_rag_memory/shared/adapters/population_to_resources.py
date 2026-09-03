from __future__ import annotations

from typing import Any, Mapping

from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.tool_registry.models import (
    PersonSchemaPolicy,
    PersonSeed,
    PersonSeedPanel,
)
from quant_pipeline.phase_03_agents_rag_memory.shared.contracts import model_or_mapping


def to_entitlement_population_view(
    person_seed_panel: Mapping[str, Any],
    validated_population_manifest: Mapping[str, Any],
    canonical_person_policy: Mapping[str, Any],
) -> tuple[PersonSeedPanel, PersonSchemaPolicy]:
    """Project population foundation output and governance ontology into S15 entitlement inputs."""

    seeds = model_or_mapping(person_seed_panel)
    source = model_or_mapping(validated_population_manifest)
    population = source["population_manifest"] if "population_manifest" in source else source
    persons = {item["person_id"]: item for item in population["persons"]}
    records: list[PersonSeed] = []
    resources: set[str] = set()
    capabilities: set[str] = set()
    for seed in seeds["records"]:
        person = persons.get(seed["person_id"])
        if person is None:
            raise ValueError(f"Seed references missing person: {seed['person_id']}")
        profile = person["profile"]
        flags = tuple(sorted(profile["resources"].get("flags", ())))
        capability_map = {str(k): float(v) for k, v in profile["capabilities"].items()}
        resources.update(flags)
        capabilities.update(capability_map)
        records.append(PersonSeed(
            person_id=seed["person_id"],
            economic_role=profile["economic_role"],
            institution=profile.get("institution_type"),
            resources=flags,
            capabilities=capability_map,
            constraints=(),
            allowed_data_classes=(),
            schema_version="person_seed_panel.v2",
        ))
    policy_source = model_or_mapping(canonical_person_policy)
    allowed_roles = tuple(sorted(policy_source["role_taxonomy"]["role_to_family"]))
    policy = PersonSchemaPolicy(
        allowed_roles=allowed_roles,
        allowed_resources=tuple(sorted(resources)),
        allowed_capabilities=tuple(sorted(capabilities)),
        allowed_constraints=(),
    )
    panel = PersonSeedPanel(records=tuple(sorted(records, key=lambda item: item.person_id)), lineage_id=seeds["lineage_id"])
    return panel, policy
