from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest
import yaml

from quant_pipeline.phase_03_agents_rag_memory.foundation.population.orchestration import (
    PopulationFoundationPipeline,
    PopulationPipelineRequest,
    PopulationPipelineStatus,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.population.s5.generation import (
    PersonalityCandidateGenerator,
    PromptAsset,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.population.s5.models import (
    ConsistencyRulesConfig,
    GenerationMode,
    GenerationRequest,
    PopulationGenerationConfig,
    PriorPopulationGenerationState,
    ProviderAdapterConfig,
    ProviderAdapterRegistryConfig,
    ProviderKind,
    RetryPolicy,
    RunContext,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.population.s5.ports import StructuredGenerationResponse
from quant_pipeline.phase_03_agents_rag_memory.foundation.population.s6.models import (
    CoverageDensityConfig,
    GenerationMode as S6Mode,
    PriorPopulationGenerationStateV2,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.population.s7.models import PopulationRepresentationConfig
from quant_pipeline.phase_03_agents_rag_memory.foundation.population.s8.models import SocialGraphConfig
from quant_pipeline.phase_03_agents_rag_memory.foundation.population import apply_mini_profile, selected_candidate_indexes
from quant_pipeline.phase_03_agents_rag_memory.shared.adapters.governance_to_population import (
    to_population_person_policy,
    to_population_tag_registry,
)


class FixtureProvider:
    def __init__(self, content: str) -> None:
        self.content = content

    async def generate_structured(self, request):  # noqa: ANN001
        return StructuredGenerationResponse(content=self.content, provider_request_id="p3-three-person-fixture")


def load_yaml(path):  # noqa: ANN001
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_three_person_society_from_structured_llm_fixture(
    root,
    governance_outputs,
    operational_policy,
    objective_aliases,
) -> None:
    tags = to_population_tag_registry(governance_outputs["personality_tag_registry"])
    policy = to_population_person_policy(
        governance_outputs["person_schema_policy"],
        governance_outputs["personality_tag_registry"],
        operational_policy,
        objective_aliases,
    )
    s5 = root / "config/population/s5"
    mini_profile = load_yaml(root / "config/population/mini_three_person_profile.yaml")
    candidate_indexes = selected_candidate_indexes(mini_profile)
    candidates = json.loads(
        (root / "fixtures/integration/provider_candidate_batch.json").read_text(encoding="utf-8")
    )["candidates"]
    candidates = [candidates[index] for index in candidate_indexes]
    generator = PersonalityCandidateGenerator(
        FixtureProvider(json.dumps({"candidates": candidates})),
        PromptAsset(
            "p3_s5_personality_candidate_generator",
            "1.0.0",
            (root / "prompts/population/personality_candidate_generator_v1.md").read_text(encoding="utf-8"),
        ),
    )
    generation_config = PopulationGenerationConfig.model_validate(
        load_yaml(s5 / "population_generation_config.yaml"), strict=False
        )
    request = GenerationRequest(
        run_context=RunContext(
            run_id="three-person-society",
            snapshot_id=governance_outputs["phase3_run_snapshot"]["identity"]["snapshot_id"],
            as_of=datetime(2026, 7, 30, 12, tzinfo=timezone.utc),
            creator_run_id="creator-three-person",
            generation_round=0,
            seed=3,
        ),
        personality_tag_registry=tags,
        person_schema_policy=policy,
        population_generation_config=generation_config,
        prior_population_generation_state=PriorPopulationGenerationState(
            creator_run_id="creator-three-person", generation_round=0, mode=GenerationMode.DENSITY
        ),
        provider_adapter_registry_config=ProviderAdapterRegistryConfig(
            registry_id="fixture-three-person",
            selected_provider_id="fixture",
            providers=(
                ProviderAdapterConfig(
                    provider_id="fixture",
                    provider_kind=ProviderKind.FIXTURE,
                    base_url="https://invalid.local/v1",
                    model_id="fixture-model",
                    timeout_seconds=10.0,
                    max_connections=1,
                    supports_strict_json_schema=True,
                ),
            ),
        ),
        retry_policy=RetryPolicy.model_validate(load_yaml(s5 / "personality_creator_retry_policy.yaml"), strict=False),
    )
    base_request = PopulationPipelineRequest(
            generation_request=request,
            consistency_rules_config=ConsistencyRulesConfig.model_validate(
                load_yaml(s5 / "personality_consistency_rules.yaml"), strict=False
            ),
            coverage_density_config=CoverageDensityConfig.model_validate(
                load_yaml(root / "config/population/s6/coverage_density_config.yaml"), strict=False
            ),
            prior_s6_state=PriorPopulationGenerationStateV2(
                creator_run_id="creator-three-person", generation_round=0, mode=S6Mode.DENSITY
            ),
            population_representation_config=PopulationRepresentationConfig.model_validate(
                load_yaml(root / "config/population/s7/population_representation_config.yaml"), strict=False
            ),
            social_graph_config=SocialGraphConfig.model_validate(
                load_yaml(root / "config/population/s8/social_graph_config.yaml"), strict=False
            ),
        )
    result = await PopulationFoundationPipeline(generator).execute(apply_mini_profile(base_request, mini_profile))
    assert result.status is PopulationPipelineStatus.READY
    assert result.population_validation is not None
    assert result.social_graph_validation is not None
    manifest = result.population_validation.validated_population_manifest.population_manifest
    graph = result.social_graph_validation.validated_initial_social_graph
    assert manifest.person_count == 3
    assert len({person.person_id for person in manifest.persons}) == 3
    assert graph.initial_social_graph.population_id == manifest.population_id
    assert graph.validation_status.value == "READY"
    assert graph.initial_social_graph.metrics.node_count == 3
