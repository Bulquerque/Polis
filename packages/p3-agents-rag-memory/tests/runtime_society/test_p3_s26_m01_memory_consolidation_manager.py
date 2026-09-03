from __future__ import annotations
import sys
from pathlib import Path
TESTS = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name != "tests" else Path(__file__).resolve().parent
if str(TESTS) not in sys.path: sys.path.insert(0, str(TESTS))
from s26_test_support import valid, invalid
import copy, pytest
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S26_M01_memory_consolidation_manager import run_module
from quant_pipeline.phase_03_agents_rag_memory.s26.errors import S26PolicyError,S26TemporalError
REQ=('current_memory_state','person_learning_trajectory_bundle','next_belief_state_panel','validated_next_person_state_panel','social_delivery_panel','active_belief_feedback_bundle','active_retro_policy_patch','memory_consolidation_config')
def inputs(): return {k:valid(k) for k in REQ}
def test_consolidates_and_emits_triggers():
    out=run_module(inputs()); state=out['next_memory_state']; triggers=out['memory_trigger_event_panel']
    assert state['created_count']>=1; assert state['reinforced_count']>=1
    assert all(x['valid_from_cycle']==state['cycle_id']+1 or x['protected_audit'] for x in state['items'] if x['status']=='ACTIVE')
    assert all(x['target_cycle']==state['cycle_id']+1 for x in triggers['records'])
def test_is_deterministic_and_does_not_mutate_inputs():
    value=inputs(); before=copy.deepcopy(value)
    assert run_module(value)==run_module(value); assert value==before
def test_named_retro_patch_fails():
    value=inputs(); value['active_retro_policy_patch']=invalid('named_memory_patch')
    with pytest.raises(S26PolicyError): run_module(value)
def test_future_event_fails():
    value=inputs(); value['social_delivery_panel']['records'][0]['status_at']='2026-01-16T00:00:00Z'
    with pytest.raises(S26TemporalError): run_module(value)
