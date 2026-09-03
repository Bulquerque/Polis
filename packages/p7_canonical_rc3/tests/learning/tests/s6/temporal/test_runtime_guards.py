import pytest
from quant_pipeline.phase_07_strategy_tournament.learning.runner_s6 import run_s6_pipeline
from quant_pipeline.phase_07_strategy_tournament.learning.domain.errors import P7S6Error
from tests.learning.tests.s6.conftest import rehash,rebuild_tournament_manifest

def test_future_feature_is_rejected(bundle,config):
    bundle['factor_adjusted_candidate_panel']['records'][0]['feature_available_at']='2025-03-02T00:00:00Z'; rehash(bundle['factor_adjusted_candidate_panel']); rebuild_tournament_manifest(bundle)
    with pytest.raises(P7S6Error) as exc: run_s6_pipeline(bundle,config)
    assert exc.value.issue.code=='P7_LTR_RUNTIME_FEATURE_FUTURE_DATED'

def test_future_model_approval_is_not_eligible(bundle,config):
    bundle['governed_model_registry']['records'][0]['approved_at']='2025-03-02T00:00:00Z'; rehash(bundle['governed_model_registry'])
    result=run_s6_pipeline(bundle,config)
    assert result['outputs']['resolved_runtime_model_reference']['record_count']==0

def test_stale_or_future_training_cutoff_is_not_eligible(bundle,config):
    model=bundle['ltr_model_artifact']['records'][0]; model['training_cutoff_at']='2025-03-01T14:30:00Z'
    old=model['model_hash']; payload=dict(model); payload.pop('model_hash'); model['model_hash']=__import__('quant_pipeline.phase_07_strategy_tournament.learning.domain.canonical',fromlist=['digest']).digest(payload)
    rehash(bundle['ltr_model_artifact'])
    for row in bundle['ltr_model_qualification_registry']['records']:
        if row['model_hash']==old: row['model_hash']=model['model_hash'];row['training_cutoff_at']=model['training_cutoff_at']
    rehash(bundle['ltr_model_qualification_registry'])
    gov=bundle['governed_model_registry']['records'][0];gov['model_hash']=model['model_hash'];rehash(bundle['governed_model_registry'])
    result=run_s6_pipeline(bundle,config)
    assert result['outputs']['resolved_runtime_model_reference']['record_count']==0
