from __future__ import annotations
import copy,yaml,pytest
from quant_pipeline.phase_03_agents_rag_memory.foundation.person_foundation.tags import load_personality_tag_registry
from quant_pipeline.phase_03_agents_rag_memory.foundation.person_foundation.errors import S4ContractError
from quant_pipeline.phase_03_agents_rag_memory.foundation.population.authority import validate_population_authority,validate_coverage_convergence,validate_graph_calibration
from phase_03_extracted.phase_03_agents_rag_memory_agent_package_RC4_1.tests.phase_specific.population_support import build_population_pipeline

def y(p): return yaml.safe_load(p.read_text(encoding="utf-8"))

def test_canonical_person_authority_and_population_lock(root):
    person=y(root/'config/governance/PERSON_SCHEMA_AUTHORITY.yaml')
    assert person['canonical_schema']=='schemas/person_profile.schema.yaml'
    assert person['alias_policy']=='ACTIVE_ALIASES_FORBIDDEN'
    assert validate_population_authority(root)['status']=='PASS'
    assert validate_coverage_convergence(y(root/'config/population/s6/coverage_density_config.yaml'))['status']=='PASS'

def test_active_tag_alias_is_rejected(root):
    value=y(root/'config/governance/PERSONALITY_TAG_REGISTRY.yaml')
    value=copy.deepcopy(value); value['categories'][0]['tags'][0]['aliases']=['old_young']
    with pytest.raises(S4ContractError,match='ACTIVE_ALIAS_FORBIDDEN'):
        load_personality_tag_registry({'personality_tag_registry_config':value})

@pytest.mark.asyncio
async def test_population_and_graph_are_stable_and_calibrated(root,governance_outputs,operational_policy,objective_aliases):
    _,_,a=await build_population_pipeline(root,governance_outputs,operational_policy,objective_aliases)
    _,_,b=await build_population_pipeline(root,governance_outputs,operational_policy,objective_aliases)
    assert a.population_build.population_manifest.population_id==b.population_build.population_manifest.population_id
    assert a.population_build.person_seed_panel.panel_hash==b.population_build.person_seed_panel.panel_hash
    ga=a.social_graph_validation.validated_initial_social_graph.initial_social_graph
    gb=b.social_graph_validation.validated_initial_social_graph.initial_social_graph
    assert ga.graph_hash==gb.graph_hash
    profile=y(root/'config/population/s8/social_graph_calibration.yaml')
    assert validate_graph_calibration(ga.metrics.model_dump(mode='json'),profile)['status']=='PASS'
