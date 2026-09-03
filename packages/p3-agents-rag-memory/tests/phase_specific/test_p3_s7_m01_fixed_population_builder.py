import pytest
from .population_support import build_population_pipeline

@pytest.mark.asyncio
async def test_population_ids_and_weights_are_stable(root, governance_outputs, operational_policy, objective_aliases):
    _, _, first = await build_population_pipeline(root, governance_outputs, operational_policy, objective_aliases)
    _, _, second = await build_population_pipeline(root, governance_outputs, operational_policy, objective_aliases)
    a = first.population_build.population_manifest.persons
    b = second.population_build.population_manifest.persons
    assert [p.person_id for p in a] == [p.person_id for p in b]
    assert abs(sum(p.representation_weight for p in a) - 1.0) < 1e-8
