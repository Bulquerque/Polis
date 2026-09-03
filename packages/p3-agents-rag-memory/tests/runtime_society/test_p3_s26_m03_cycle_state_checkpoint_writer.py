from __future__ import annotations
import sys
from pathlib import Path
TESTS = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name != "tests" else Path(__file__).resolve().parent
if str(TESTS) not in sys.path: sys.path.insert(0, str(TESTS))
from s26_test_support import valid, invalid
import copy, json
from pathlib import Path
import pytest
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S26_M03_cycle_state_checkpoint_writer import run_module
from quant_pipeline.phase_03_agents_rag_memory.s26.artifacts import CycleStateSnapshotOut
from quant_pipeline.phase_03_agents_rag_memory.s26.errors import S26LineageError
from quant_pipeline.phase_03_agents_rag_memory.s26.errors import S26PersistenceError
from quant_pipeline.phase_03_agents_rag_memory.s26.storage import read_checkpoint, write_checkpoint_atomic
REQ=('validated_next_person_state_panel','next_belief_state_panel','next_memory_state','next_social_graph','next_cycle_endogenous_stimulus_queue','phase3_run_snapshot','belief_outcome_commitment_log')
def inputs(): return {k:valid(k) for k in REQ}
def test_checkpoint_is_complete_and_deterministic():
    first=run_module(inputs())['cycle_state_snapshot_out']; second=run_module(inputs())['cycle_state_snapshot_out']
    assert first==second; assert first['target_cycle_id']==first['source_cycle_id']+1
    assert len(first['artifact_manifest'])==6
    assert all(first[k] for k in ('foundation_manifest_ref','config_manifest_ref','prompt_manifest_ref','model_registry_ref','provider_fingerprint_ref','replay_cache_ref'))
def test_append_only_commitments():
    value=inputs(); value['phase3_run_snapshot']={**value['phase3_run_snapshot'],'prior_commitment_ids':['missing']}
    with pytest.raises(S26LineageError): run_module(value)
def test_atomic_write_roundtrip(tmp_path:Path):
    raw=run_module(inputs())['cycle_state_snapshot_out']; model=CycleStateSnapshotOut.model_validate(raw)
    path=write_checkpoint_atomic(model,tmp_path/'checkpoint.json')
    assert read_checkpoint(path)==model
    assert not list(tmp_path.glob('*.tmp'))
def test_tampered_checkpoint_fails(tmp_path:Path):
    raw=run_module(inputs())['cycle_state_snapshot_out']; model=CycleStateSnapshotOut.model_validate(raw)
    path=write_checkpoint_atomic(model,tmp_path/'checkpoint.json'); value=json.loads(path.read_text()); value['target_cycle_id']+=1; path.write_text(json.dumps(value))
    with pytest.raises(S26PersistenceError, match="checkpoint"):
        read_checkpoint(path)
