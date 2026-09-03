import pytest
from .population_support import build_population_pipeline

@pytest.mark.asyncio
async def test_population_validation_has_no_duplicate_people(root, governance_outputs, operational_policy, objective_aliases):
    _, _, result = await build_population_pipeline(root, governance_outputs, operational_policy, objective_aliases)
    validated = result.population_validation.validated_population_manifest
    ids = [p.person_id for p in validated.population_manifest.persons]
    assert len(ids) == len(set(ids))
    assert validated.validation_status.value == "READY"
