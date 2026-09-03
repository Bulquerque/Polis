from __future__ import annotations
import sys
from pathlib import Path
TESTS = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name != "tests" else Path(__file__).resolve().parent
if str(TESTS) not in sys.path: sys.path.insert(0, str(TESTS))
from s26_test_support import valid, invalid
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S26_M01_memory_consolidation_manager import run_module as m1
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S26_M02_endogenous_stimulus_queue_checkpoint_writer import run_module as m2
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S26_M03_cycle_state_checkpoint_writer import run_module as m3

def test_full_s26_flow():
    one=m1({k:valid(k) for k in ('current_memory_state','person_learning_trajectory_bundle','next_belief_state_panel','validated_next_person_state_panel','social_delivery_panel','active_belief_feedback_bundle','active_retro_policy_patch','memory_consolidation_config')})
    two_inputs={k:valid(k) for k in ('tool_discovery_event_panel','social_delivery_event_panel','finalized_attention_followup_intent_panel','phase3_run_snapshot','stimulus_bus_config')}; two_inputs['memory_trigger_event_panel']=one['memory_trigger_event_panel']
    two=m2(two_inputs)
    three_inputs={k:valid(k) for k in ('validated_next_person_state_panel','next_belief_state_panel','next_social_graph','phase3_run_snapshot','belief_outcome_commitment_log')}; three_inputs['next_memory_state']=one['next_memory_state']; three_inputs.update(two)
    checkpoint=m3(three_inputs)['cycle_state_snapshot_out']
    assert checkpoint['target_cycle_id']==checkpoint['source_cycle_id']+1
    assert checkpoint['memory_state_ref'] and checkpoint['endogenous_stimulus_queue_ref']
