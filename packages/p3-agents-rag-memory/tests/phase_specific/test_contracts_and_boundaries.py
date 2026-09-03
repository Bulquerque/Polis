
from .helpers import yaml_load

def test_external_contract_surface_is_exact(plan_root):
    inp=yaml_load(plan_root/'contracts'/'INPUT_CONTRACTS.yaml')
    out=yaml_load(plan_root/'contracts'/'OUTPUT_CONTRACTS.yaml')
    assert inp['required_boundary_inputs']==['FoundationRuntimeManifest','CycleKernelRequest']
    assert out['official_outputs']==['social_feature_panel','evidence_tag_panel','agent_disagreement_panel','context_memory_feature_panel','hypothesis_registry','phase4_social_handoff_manifest']

def test_connection_boundary_blocks_direct_future_phase_authority(plan_root):
    c=yaml_load(plan_root/'contracts'/'CONNECTIONS.yaml')
    forbidden=set(c['forbidden'])
    assert 'direct_P3_to_P5_P6_P7_P8' in forbidden
    assert 'future_phase_output_into_current_cognition' in forbidden
    assert 'same_cycle_back_edge' in forbidden

def test_variable_evolution_boundary_preserves_phase_authority(plan_root):
    b=yaml_load(plan_root/'cross_phase'/'contracts'/'VARIABLE_EVOLUTION_BOUNDARY.yaml')
    text=str(b).lower()
    assert 'p3' in text and 'p4' in text and 'p9' in text
    assert 'feature' in text

def test_retro_outputs_are_next_cycle_only(plan_root):
    io=yaml_load(plan_root/'contracts'/'TEMPORAL_EDGES.yaml')
    pairs={(e['from_artifact'],e['to_artifact']) for e in io['temporal_edges']}
    assert ('next_cycle_retro_update_package','retro_memory_update_package') in pairs
    assert ('next_cycle_retro_handoff_manifest','phase3_retro_handoff_manifest') in pairs

def test_reward_vector_is_not_sharpe_only(plan_root):
    cfg=yaml_load(plan_root/'cross_phase'/'p9_context_learning'/'config'/'reward_vector_config.yaml')
    text=str(cfg).lower()
    for term in ['predictive','incremental','stability','economic','complexity']:
        assert term in text
