import pytest
from .population_support import build_population_pipeline

@pytest.mark.asyncio
async def test_candidate_consistency_returns_only_valid_candidates(root, governance_outputs, operational_policy, objective_aliases):
    _, _, result = await build_population_pipeline(root, governance_outputs, operational_policy, objective_aliases)
    pool = result.validated_candidates
    assert pool.accepted_candidates
    assert all(item.candidate_id for item in pool.accepted_candidates)
