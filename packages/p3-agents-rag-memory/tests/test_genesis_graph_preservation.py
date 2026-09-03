from quant_pipeline.phase_03_agents_rag_memory.shared.adapters.population_to_warmup import to_replay_graph_view,to_replay_person_seed_panel
from quant_pipeline.phase_03_agents_rag_memory.foundation.warmup_memory.replay.service import GenesisStateFactory
from quant_pipeline.phase_03_agents_rag_memory.foundation.warmup_memory.replay.models import WarmupEventScheduleView,WarmupCheckpointPlanView,FoundationResourceManifest,RetroPolicyPatchView
import json

def test_genesis_preserves_population_edge_values(governance_outputs, population_outputs,root):
    run=governance_outputs['phase3_run_snapshot']['identity']['run_id']; sid=governance_outputs['phase3_run_snapshot']['identity']['snapshot_id']
    seeds=to_replay_person_seed_panel(population_outputs['person_seed_panel'],population_outputs['validated_population_manifest'],run_id=run,snapshot_id=sid)
    graph=to_replay_graph_view(population_outputs['validated_initial_social_graph'],population_outputs['validated_population_manifest'],run_id=run,snapshot_id=sid)
    # Reuse strict, schema-qualified genesis state fixtures, replacing identity/population inputs only.
    valid=root/'fixtures/warmup_memory/s11/valid'
    schedule=json.loads((valid/'warmup_event_schedule_genesis.json').read_text()); plan=json.loads((valid/'warmup_checkpoint_plan_genesis.json').read_text())
    schedule.update({'run_id':run,'snapshot_id':sid})
    plan.update({'run_id':run,'snapshot_id':sid,'schedule_hash':schedule['schedule_hash']})
    # Hash fields are validated by orchestrator, not GenesisStateFactory itself.
    resources=FoundationResourceManifest.model_validate(json.loads((valid/'canonical_cycle_pipeline_config.json').read_text())['foundation_resource_manifest'])
    resources=resources.model_copy(update={'run_id':run,'snapshot_id':sid})
    patch=RetroPolicyPatchView.model_validate(json.loads((valid/'active_retro_policy_patch.json').read_text())).model_copy(update={'run_id':run,'snapshot_id':sid})
    state=GenesisStateFactory().build(schedule=WarmupEventScheduleView.model_validate(schedule),checkpoint_plan=WarmupCheckpointPlanView.model_validate(plan),person_seed_panel=seeds,social_graph=graph,resources=resources,retro_patch=patch)
    edge=state.social_graph.records[0]; source=graph.records[0]
    assert edge.trust==source.trust and edge.strength==source.strength
    assert edge.domain_trust==source.domain_trust and edge.influence==source.influence
