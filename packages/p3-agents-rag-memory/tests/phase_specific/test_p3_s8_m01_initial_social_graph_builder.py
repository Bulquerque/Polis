import pytest
from .population_support import build_population_pipeline

@pytest.mark.asyncio
async def test_initial_graph_is_deterministic(root, governance_outputs, operational_policy, objective_aliases):
    _, _, first = await build_population_pipeline(root, governance_outputs, operational_policy, objective_aliases)
    _, _, second = await build_population_pipeline(root, governance_outputs, operational_policy, objective_aliases)
    assert first.social_graph_build.initial_social_graph.graph_hash == second.social_graph_build.initial_social_graph.graph_hash
