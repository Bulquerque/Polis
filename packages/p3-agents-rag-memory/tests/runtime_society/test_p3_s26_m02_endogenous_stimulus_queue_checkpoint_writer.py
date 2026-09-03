from __future__ import annotations
import sys
from pathlib import Path
TESTS = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name != "tests" else Path(__file__).resolve().parent
if str(TESTS) not in sys.path: sys.path.insert(0, str(TESTS))
from s26_test_support import valid, invalid
import copy,pytest
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S26_M02_endogenous_stimulus_queue_checkpoint_writer import run_module
from quant_pipeline.phase_03_agents_rag_memory.s26.errors import S26ContractError
REQ=('tool_discovery_event_panel','social_delivery_event_panel','memory_trigger_event_panel','finalized_attention_followup_intent_panel','phase3_run_snapshot','stimulus_bus_config')
def inputs(): return {k:valid(k) for k in REQ}
def test_queue_targets_exactly_next_cycle():
    q=run_module(inputs())['next_cycle_endogenous_stimulus_queue']
    assert q['target_cycle_id']==q['source_cycle_id']+1
    assert all(x['target_cycle']==q['target_cycle_id'] for x in q['stimuli'])
def test_deterministic_and_ordered():
    value=inputs(); first=run_module(value); second=run_module(copy.deepcopy(value))
    assert first==second
    keys=[(x['target_cycle'],x['available_at'],-x['priority'],x['target_person_id'],x['stimulus_id']) for x in first['next_cycle_endogenous_stimulus_queue']['stimuli']]
    assert keys==sorted(keys)
def test_empty_sources_are_valid():
    value=inputs()
    for key in ('tool_discovery_event_panel','social_delivery_event_panel','memory_trigger_event_panel','finalized_attention_followup_intent_panel'):
        value[key]={**value[key], 'records':[]}
    assert run_module(value)['next_cycle_endogenous_stimulus_queue']['stimuli']==[]
def test_budget_overflow_blocks():
    value=inputs(); value['stimulus_bus_config']={**value['stimulus_bus_config'],'max_stimuli_per_person':1}
    with pytest.raises(S26ContractError): run_module(value)
