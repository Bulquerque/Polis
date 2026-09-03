from __future__ import annotations

from datetime import datetime, timezone

import pytest
import yaml

from quant_pipeline.phase_03_agents_rag_memory.foundation.population.orchestration import PopulationPipelineRequest, PopulationPipelineStatus, PopulationFoundationPipeline
from quant_pipeline.phase_03_agents_rag_memory.foundation.population.s5.generation import PersonalityCandidateGenerator, PromptAsset
from quant_pipeline.phase_03_agents_rag_memory.foundation.population.s5.models import (
    ConsistencyRulesConfig, GenerationMode, GenerationRequest, PopulationGenerationConfig,
    PriorPopulationGenerationState, ProviderAdapterConfig, ProviderAdapterRegistryConfig,
    ProviderKind, RetryPolicy, RunContext,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.population.s5.ports import StructuredGenerationResponse
from quant_pipeline.phase_03_agents_rag_memory.foundation.population.s6.models import CoverageDensityConfig, GenerationMode as S6Mode, PriorPopulationGenerationStateV2
from quant_pipeline.phase_03_agents_rag_memory.foundation.population.s7.models import PopulationRepresentationConfig
from quant_pipeline.phase_03_agents_rag_memory.foundation.population.s8.models import SocialGraphConfig
from quant_pipeline.phase_03_agents_rag_memory.shared.adapters.governance_to_population import to_population_person_policy,to_population_tag_registry

class FixtureProvider:
    def __init__(self, content: str): self.content=content
    async def generate_structured(self, request):
        return StructuredGenerationResponse(content=self.content,provider_request_id='p3r4-population_outputs-e2e')

def y(path): return yaml.safe_load(path.read_text(encoding='utf-8'))

@pytest.mark.integration
@pytest.mark.asyncio
async def test_governance_authority_drives_population_pipeline(root,governance_outputs,operational_policy,objective_aliases):
    tags=to_population_tag_registry(governance_outputs['personality_tag_registry'])
    policy=to_population_person_policy(governance_outputs['person_schema_policy'],governance_outputs['personality_tag_registry'],operational_policy,objective_aliases)
    s5=root/'config/population/s5'
    prompt=PromptAsset('p3_s5_personality_candidate_generator','1.0.0',(root/'prompts/population/personality_candidate_generator_v1.md').read_text())
    provider=FixtureProvider((root/'fixtures/integration/provider_candidate_batch.json').read_text())
    generator=PersonalityCandidateGenerator(provider,prompt)
    generation_config=PopulationGenerationConfig.model_validate(y(s5/'population_generation_config.yaml'),strict=False).model_copy(update={'requested_batch_size':25})
    request=GenerationRequest(
      run_context=RunContext(run_id='test-run-001',snapshot_id=governance_outputs['phase3_run_snapshot']['identity']['snapshot_id'],as_of=datetime(2026,7,27,12,tzinfo=timezone.utc),creator_run_id='creator-p3r4',generation_round=0,seed=42),
      personality_tag_registry=tags,person_schema_policy=policy,population_generation_config=generation_config,
      prior_population_generation_state=PriorPopulationGenerationState(creator_run_id='creator-p3r4',generation_round=0,mode=GenerationMode.DENSITY),
      provider_adapter_registry_config=ProviderAdapterRegistryConfig(registry_id='fixture',selected_provider_id='fixture',providers=(ProviderAdapterConfig(provider_id='fixture',provider_kind=ProviderKind.FIXTURE,base_url='https://invalid.local/v1',model_id='fixture-model',timeout_seconds=10.0,max_connections=1,supports_strict_json_schema=True),)),
      retry_policy=RetryPolicy.model_validate(y(s5/'personality_creator_retry_policy.yaml'),strict=False),
    )
    pipeline=PopulationFoundationPipeline(generator)
    result=await pipeline.execute(PopulationPipelineRequest(
      generation_request=request,
      consistency_rules_config=ConsistencyRulesConfig.model_validate(y(s5/'personality_consistency_rules.yaml'),strict=False),
      coverage_density_config=CoverageDensityConfig.model_validate(y(root/'config/population/s6/coverage_density_config.yaml'),strict=False).model_copy(update={'target_population_size':25,'minimum_novelty_rounds':1,'patience_rounds':1,'density_radius':10.0}),
      prior_s6_state=PriorPopulationGenerationStateV2(creator_run_id='creator-p3r4',generation_round=0,mode=S6Mode.DENSITY),
      population_representation_config=PopulationRepresentationConfig.model_validate(y(root/'config/population/s7/population_representation_config.yaml'),strict=False),
      social_graph_config=SocialGraphConfig.model_validate(y(root/'config/population/s8/social_graph_config.yaml'),strict=False),
    ))
    assert result.status is PopulationPipelineStatus.READY
    assert result.population_validation is not None
    assert result.social_graph_validation is not None
    assert result.social_graph_validation.validated_initial_social_graph.validation_status.value=='READY'
