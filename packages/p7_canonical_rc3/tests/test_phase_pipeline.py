from __future__ import annotations
import json, yaml
from pathlib import Path
from quant_pipeline.phase_07_strategy_tournament import run_runtime_from_foundation
from quant_pipeline.phase_07_strategy_tournament.handoffs import prepare_tournament_inputs, prepare_learning_inputs, prepare_finalization_inputs
from quant_pipeline.phase_07_strategy_tournament.tournament.pipeline import run_tournament_pipeline
from quant_pipeline.phase_07_strategy_tournament.learning.runner_s6 import run_s6_pipeline

ROOT=Path(__file__).resolve().parents[1]
def load(path): return json.loads((ROOT/path).read_text())
def yload(path): return yaml.safe_load((ROOT/path).read_text())

def configs():
    tournament={"execution_time":"2026-01-05T14:30:00Z","strict_hash_validation":True,"emit_debug_events":False,"numerical_tolerance":1e-10}
    learning=yload('configs/learning/s6_default_config.yaml'); learning['context'].update({"run_id":"run-p7","cycle_id":"cycle-2","decision_time":"2026-01-05T14:30:00Z","created_at":"2026-01-05T14:30:00Z","lineage_id":"lineage-p7"})
    safety=load('fixtures/finalization/input/s7_config_fixture.json'); publication=load('fixtures/finalization/input/s8_config_fixture.json')
    for cfg in (safety, publication): cfg['runtime'].update({"run_id":"run-p7","trace_id":"trace-p7","run_timestamp":"2026-01-05T14:30:00Z"})
    return tournament, learning, safety, publication

def test_foundation_to_tournament_transition_and_tournament_executes():
    foundation=load('fixtures/foundation/foundation_to_tournament_handoff_fixture.json')
    tournament_inputs=prepare_tournament_inputs(foundation)
    result=run_tournament_pipeline(tournament_inputs,configs()[0])
    assert result['status']=='PASS'
    assert result['outputs']['interpretable_score_panel']['record_count']==1

def test_tournament_to_learning_transition_and_interpretable_runtime_executes():
    foundation=load('fixtures/foundation/foundation_to_tournament_handoff_fixture.json')
    tournament_inputs=prepare_tournament_inputs(foundation); tournament=run_tournament_pipeline(tournament_inputs,configs()[0])
    bundle=prepare_learning_inputs(tournament['outputs'],foundation)
    cfg=configs()[1]; cfg['runtime_policy']['requested_mode']='INTERPRETABLE_ONLY'; cfg['runtime_policy']['fallback_mode']='INTERPRETABLE_ONLY'
    out=run_s6_pipeline(bundle,cfg)['outputs']
    assert out['hybrid_candidate_score_panel']['record_count']==1
    assert out['hybrid_candidate_score_panel']['records'][0]['hybrid_status']=='INTERPRETABLE_FALLBACK'

def test_full_sequential_runtime_pipeline():
    foundation=load('fixtures/foundation/foundation_to_tournament_handoff_fixture.json')
    tournament, learning, safety, publication = configs()
    result=run_runtime_from_foundation(
        foundation,
        tournament_config=tournament,
        learning_config=learning,
        safety_config=safety,
        publication_config=publication,
    )
    assert result['status']=='PASS'
    final=result['outputs']
    assert final['ranked_strategy_candidate_panel']['record_count'] == 0
    assert final['abstained_candidate_panel']['record_count'] == 1
    assert final['phase8_strategy_ranking_handoff_manifest']['record_count']==1
    assert final['ranking_audit_report']['records'][0]['candidate_conservation_pass'] is True

def test_full_pipeline_is_deterministic_and_publishes_release():
    foundation=load('fixtures/foundation/foundation_to_tournament_handoff_fixture.json')
    args=configs()
    first=run_runtime_from_foundation(
        foundation,
        tournament_config=args[0],
        learning_config=args[1],
        safety_config=args[2],
        publication_config=args[3],
    )
    args=configs()
    second=run_runtime_from_foundation(
        foundation,
        tournament_config=args[0],
        learning_config=args[1],
        safety_config=args[2],
        publication_config=args[3],
    )
    assert first['outputs']['abstained_candidate_panel']['content_sha256'] == second['outputs']['abstained_candidate_panel']['content_sha256']
    assert first['outputs']['p7_phase_release_receipt']['records'][0]['technical_closure'] is True
    assert first['outputs']['p7_phase_release_receipt']['records'][0]['production_promotion_allowed'] is False
