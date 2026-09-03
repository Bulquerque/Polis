import pytest
from .population_support import build_population_pipeline

@pytest.mark.asyncio
async def test_initial_graph_contains_only_population_nodes(root, governance_outputs, operational_policy, objective_aliases):
    _, _, result = await build_population_pipeline(root, governance_outputs, operational_policy, objective_aliases)
    persons = {p.person_id for p in result.population_validation.validated_population_manifest.population_manifest.persons}
    graph = result.social_graph_validation.validated_initial_social_graph
    assert graph.validation_status.value == "READY"
    assert all(edge.source_person_id in persons and edge.target_person_id in persons for edge in graph.initial_social_graph.edges)
    assert all(edge.source_person_id != edge.target_person_id for edge in graph.initial_social_graph.edges)
