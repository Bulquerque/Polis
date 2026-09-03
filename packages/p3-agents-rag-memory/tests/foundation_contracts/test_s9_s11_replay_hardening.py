from __future__ import annotations
from datetime import datetime,date
import copy,yaml,pytest
from quant_pipeline.phase_03_agents_rag_memory.foundation.warmup_memory.checkpoint_integrity import build_checkpoint_envelope,validate_checkpoint_envelope,CheckpointIntegrityError
from quant_pipeline.phase_03_agents_rag_memory.foundation.warmup_memory.scheduling.calendar_policy import normalize_to_utc,is_business_day,validate_calendar_policy,CalendarPolicyError
from quant_pipeline.phase_03_agents_rag_memory.foundation.warmup_memory.replay.migrations import migrate_replay_state,ReplayStateMigrationError

def y(p): return yaml.safe_load(p.read_text(encoding='utf-8'))

def test_checkpoint_missing_corrupt_and_old_version_fail():
    value=build_checkpoint_envelope({'run_id':'r','records':[]},checkpoint_id='c1')
    assert validate_checkpoint_envelope(value)['checkpoint_id']=='c1'
    broken=copy.deepcopy(value); broken['payload']['records'].append({'x':1})
    with pytest.raises(CheckpointIntegrityError,match='corrupted'): validate_checkpoint_envelope(broken)
    old=copy.deepcopy(value); old['state_schema_version']='0.9.0'
    with pytest.raises(CheckpointIntegrityError,match='unsupported'): validate_checkpoint_envelope(old)
    with pytest.raises(CheckpointIntegrityError): validate_checkpoint_envelope({})

def test_calendar_timezone_holidays(root):
    policy=y(root/'config/warmup_memory/CALENDAR_POLICY.yaml')
    assert validate_calendar_policy(policy)['status']=='PASS'
    observed=normalize_to_utc(datetime(2026,7,29,9,0,0),'America/Sao_Paulo')
    assert observed.hour==12
    assert not is_business_day(date(2026,7,25),holiday_dates=set())
    assert not is_business_day(date(2026,1,1),holiday_dates={date(2026,1,1)})

def test_replay_state_migration_is_explicit_and_idempotent():
    v1={'schema_version':'1.0.0','run_id':'r','snapshot_id':'s','person_state':{'records':[]}}
    v2=migrate_replay_state(v1)
    assert v2['schema_version']=='2.0.0' and v2['migration_lineage'][-1]['migration_id']=='replay-state-v1-to-v2'
    assert migrate_replay_state(v2)==v2
    with pytest.raises(ReplayStateMigrationError): migrate_replay_state({'schema_version':'0.1.0'})

def test_explicit_genesis_implementation_exists(root):
    source=(root/'src/quant_pipeline/phase_03_agents_rag_memory/foundation/warmup_memory/replay/service.py').read_text()
    assert 'class GenesisStateFactory' in source
    assert 'Pure and deterministic genesis-state builder' in source
