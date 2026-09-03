from decimal import Decimal
import pytest
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_state import ReplayEvent
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.replay import replay_hash,replay_state,validate_event_sequence

def test_replay_state(replay_events):
    state=replay_state(replay_events)
    assert state['positions']['A']=='2'; assert state['cash']=='-21'
    assert state['allocations']['c1|A']=='2'; assert state['last_sequence']==2

def test_empty_replay():
    assert replay_state(())['last_sequence']==-1
    assert len(replay_hash(()))==64

def test_invalid_type_rejected(context):
    event=ReplayEvent(sequence=0,event_id='x',event_type='UNKNOWN')
    with pytest.raises(ValueError): replay_state((event,))

def test_sequence_validation(replay_events):
    assert validate_event_sequence(replay_events)
    duplicate=(replay_events[0],replay_events[0])
    assert not validate_event_sequence(duplicate)
