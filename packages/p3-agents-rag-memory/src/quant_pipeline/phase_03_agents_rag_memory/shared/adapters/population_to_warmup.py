from __future__ import annotations

from typing import Any, Mapping

from quant_pipeline.phase_03_agents_rag_memory.shared.contracts import model_or_mapping
from quant_pipeline.phase_03_agents_rag_memory.foundation.warmup_memory.scheduling.models import (
    SocialEdge as ScheduleSocialEdge,
    ValidatedInitialSocialGraphView as ScheduleGraphView,
    ValidatedPopulationManifestView as SchedulePopulationView,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.warmup_memory.replay.models import (
    InitialSocialEdge,
    InitialSocialGraphView,
    PersonSeed,
    PersonSeedPanelView,
)


def _population(source: Mapping[str, Any]) -> dict[str, Any]:
    data = model_or_mapping(source)
    return data["population_manifest"] if "population_manifest" in data else data


def to_schedule_population_view(
    validated_population_manifest: Mapping[str, Any],
    *,
    run_id: str,
    snapshot_id: str,
) -> SchedulePopulationView:
    source = model_or_mapping(validated_population_manifest)
    population = _population(source)
    return SchedulePopulationView.model_validate({
        "schema_id": "validated_population_manifest.v2",
        "schema_version": "2.0.0",
        "artifact_id": f"validated-population-{source.get('validated_manifest_hash', population['manifest_hash'])[:24]}",
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "population_hash": population["manifest_hash"],
        "persons": tuple(
            {"person_id": person["person_id"], "representation_weight": person["representation_weight"]}
            for person in population["persons"]
        ),
        "lineage_id": source["lineage_id"],
    }, strict=True)


def to_replay_person_seed_panel(
    person_seed_panel: Mapping[str, Any],
    validated_population_manifest: Mapping[str, Any],
    *,
    run_id: str,
    snapshot_id: str,
) -> PersonSeedPanelView:
    seeds = model_or_mapping(person_seed_panel)
    population_source = model_or_mapping(validated_population_manifest)
    population = _population(population_source)
    persons = {person["person_id"]: person for person in population["persons"]}
    records: list[PersonSeed] = []
    for seed in seeds["records"]:
        person = persons.get(seed["person_id"])
        if person is None:
            raise ValueError(f"Seed references person absent from validated population: {seed['person_id']}")
        if person["person_seed"] != seed["person_seed"]:
            raise ValueError(f"Seed mismatch for {seed['person_id']}")
        records.append(PersonSeed(
            person_id=seed["person_id"],
            representation_weight=person["representation_weight"],
            deterministic_seed=seed["person_seed"],
            structural_profile_hash=person["profile_fingerprint"],
        ))
    return PersonSeedPanelView.model_validate({
        "schema_id": "person_seed_panel.v2",
        "schema_version": "2.0.0",
        "artifact_id": f"person-seeds-{seeds['panel_hash'][:24]}",
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "population_hash": population["manifest_hash"],
        "persons": tuple(records),
        "lineage_id": seeds["lineage_id"],
    }, strict=True)


def _edge_payload(edge: Mapping[str, Any]) -> dict[str, object]:
    return {
        "edge_id": edge["edge_id"],
        "source_person_id": edge["source_person_id"],
        "target_person_id": edge["target_person_id"],
        "relationship_type": edge["relationship_type"],
        "trust": edge["global_trust"],
        "strength": edge["interaction_frequency"],
        "influence": edge["influence"],
        "interaction_frequency": edge["interaction_frequency"],
        "selection_probability": edge["selection_probability"],
        "domain_trust": {item["domain_id"]: item["value"] for item in edge["domain_trust"]},
        "origin": edge["origin"],
    }


def to_schedule_graph_view(
    validated_graph: Mapping[str, Any],
    validated_population_manifest: Mapping[str, Any],
    *,
    run_id: str,
    snapshot_id: str,
) -> ScheduleGraphView:
    source = model_or_mapping(validated_graph)
    graph = source["initial_social_graph"] if "initial_social_graph" in source else source
    population = _population(validated_population_manifest)
    return ScheduleGraphView.model_validate({
        "schema_id": "validated_initial_social_graph.v2",
        "schema_version": "2.0.0",
        "artifact_id": f"validated-graph-{source.get('validated_graph_hash', graph['graph_hash'])[:24]}",
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "population_hash": population["manifest_hash"],
        "graph_hash": graph["graph_hash"],
        "records": tuple(
            ScheduleSocialEdge(
                edge_id=edge["edge_id"],
                source_person_id=edge["source_person_id"],
                target_person_id=edge["target_person_id"],
                relationship_type=edge["relationship_type"],
            )
            for edge in graph["edges"]
        ),
        "lineage_id": source["lineage_id"],
    }, strict=True)


def to_replay_graph_view(
    validated_graph: Mapping[str, Any],
    validated_population_manifest: Mapping[str, Any],
    *,
    run_id: str,
    snapshot_id: str,
) -> InitialSocialGraphView:
    """Preserve population trust, interaction strength, influence and domain trust for genesis state."""

    source = model_or_mapping(validated_graph)
    graph = source["initial_social_graph"] if "initial_social_graph" in source else source
    population = _population(validated_population_manifest)
    records = [InitialSocialEdge.model_validate(_edge_payload(edge), strict=True) for edge in graph["edges"]]
    return InitialSocialGraphView.model_validate({
        "schema_id": "validated_initial_social_graph.v2",
        "schema_version": "2.0.0",
        "artifact_id": f"validated-graph-{source.get('validated_graph_hash', graph['graph_hash'])[:24]}",
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "population_hash": population["manifest_hash"],
        "graph_hash": graph["graph_hash"],
        "records": tuple(records),
        "lineage_id": source["lineage_id"],
    }, strict=True)
