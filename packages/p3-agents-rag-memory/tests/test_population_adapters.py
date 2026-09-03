from quant_pipeline.phase_03_agents_rag_memory.shared.adapters.population_to_warmup import to_replay_graph_view,to_replay_person_seed_panel,to_schedule_graph_view,to_schedule_population_view
from quant_pipeline.phase_03_agents_rag_memory.shared.adapters.population_to_resources import to_entitlement_population_view

def test_population_to_warmup_preserves_population_and_graph(governance_outputs, population_outputs):
    snap=governance_outputs['phase3_run_snapshot']; run=snap['identity']['run_id']; sid=snap['identity']['snapshot_id']
    seeds=to_replay_person_seed_panel(population_outputs['person_seed_panel'],population_outputs['validated_population_manifest'],run_id=run,snapshot_id=sid)
    graph=to_replay_graph_view(population_outputs['validated_initial_social_graph'],population_outputs['validated_population_manifest'],run_id=run,snapshot_id=sid)
    original=population_outputs['validated_initial_social_graph']['initial_social_graph']['edges'][0]
    projected=next(x for x in graph.records if x.edge_id==original['edge_id'])
    assert projected.trust==original['global_trust']
    assert projected.strength==original['interaction_frequency']
    assert projected.influence==original['influence']
    assert projected.domain_trust[original['domain_trust'][0]['domain_id']]==original['domain_trust'][0]['value']
    assert len(seeds.persons)==len(population_outputs['person_seed_panel']['records'])

def test_population_schedule_views(governance_outputs, population_outputs):
    snap=governance_outputs['phase3_run_snapshot']; run=snap['identity']['run_id']; sid=snap['identity']['snapshot_id']
    p=to_schedule_population_view(population_outputs['validated_population_manifest'],run_id=run,snapshot_id=sid)
    g=to_schedule_graph_view(population_outputs['validated_initial_social_graph'],population_outputs['validated_population_manifest'],run_id=run,snapshot_id=sid)
    assert p.population_hash==g.population_hash

def test_population_to_entitlement(governance_outputs, population_outputs):
    view,_=to_entitlement_population_view(population_outputs['person_seed_panel'],population_outputs['validated_population_manifest'],governance_outputs['person_schema_policy'])
    assert len(view.records)==len(population_outputs['person_seed_panel']['records'])
