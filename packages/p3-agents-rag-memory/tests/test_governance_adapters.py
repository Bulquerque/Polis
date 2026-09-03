from quant_pipeline.phase_03_agents_rag_memory.shared.adapters.governance_to_population import to_population_person_policy,to_population_tag_registry
from quant_pipeline.phase_03_agents_rag_memory.shared.adapters.governance_to_warmup import to_history_snapshot_view,to_memory_snapshot_view,to_warmup_retro_patch
from quant_pipeline.phase_03_agents_rag_memory.shared.adapters.governance_to_resources import to_knowledge_snapshot

def test_governance_to_population(governance_outputs,operational_policy,objective_aliases):
    tags=to_population_tag_registry(governance_outputs['personality_tag_registry'])
    policy=to_population_person_policy(governance_outputs['person_schema_policy'],governance_outputs['personality_tag_registry'],operational_policy,objective_aliases)
    assert set(policy.allowed_tag_ids).issubset(tags.tag_ids())
    assert policy.schema_id=='person_schema_policy.v2'

def test_governance_snapshot_views(governance_outputs):
    h=to_history_snapshot_view(governance_outputs['phase3_run_snapshot']); m=to_memory_snapshot_view(governance_outputs['phase3_run_snapshot']); k=to_knowledge_snapshot(governance_outputs['phase3_run_snapshot'])
    assert h.run_id==m.run_id==k.run_id=='test-run-001'
    assert h.snapshot_id==m.snapshot_id==k.snapshot_id
    assert h.snapshot_hash==governance_outputs['phase3_run_snapshot']['snapshot_hash']

def test_no_patch_is_explicit(governance_outputs):
    patch=to_warmup_retro_patch(governance_outputs['active_retro_policy_patch'])
    assert patch.status=='NO_PATCH' and patch.prompt_policy_ref is None

def test_governance_person_policy_to_memory_view(governance_outputs):
    from quant_pipeline.phase_03_agents_rag_memory.shared.adapters.governance_to_warmup import to_memory_person_policy_view
    view = to_memory_person_policy_view(governance_outputs['person_schema_policy'])
    assert set(item.value for item in view.allowed_memory_types) == {'EPISODIC','SEMANTIC','PROCEDURAL','SOCIAL'}
    assert view.content_hash == governance_outputs['person_schema_policy']['policy_hash']
