import pytest
from quant_pipeline.phase_03_agents_rag_memory.foundation.population.orchestration import PopulationPipelineStatus
from .population_support import build_population_pipeline

@pytest.mark.asyncio
async def test_candidate_generation_is_seeded_and_audited(root, governance_outputs, operational_policy, objective_aliases):
    _, _, result = await build_population_pipeline(root, governance_outputs, operational_policy, objective_aliases)
    assert result.status is PopulationPipelineStatus.READY
    audit = result.generation.personality_creator_generation_audit
    assert audit.attempts[0].provider_request_id == "p3-population-generation"
    assert audit.seed == 42
