from quant_pipeline.phase_07_strategy_tournament.learning.runner_s6 import run_s6_pipeline
from tests.learning.tests.s6.conftest import rehash

def test_interpretable_only_does_not_use_model(bundle,config):
    config['runtime_policy']['requested_mode']='INTERPRETABLE_ONLY'
    result=run_s6_pipeline(bundle,config); rows=result['outputs']['hybrid_candidate_score_panel']['records']
    assert all(r['hybrid_score']==r['interpretable_score'] for r in rows)
    assert all(r['model_hash'] is None for r in rows)

def test_shadow_scores_but_does_not_influence(bundle,config):
    config['runtime_policy']['requested_mode']='LTR_SHADOW'
    result=run_s6_pipeline(bundle,config); rows=result['outputs']['hybrid_candidate_score_panel']['records']
    assert all(r['hybrid_status']=='SHADOW' for r in rows)
    assert all(r['hybrid_score']==r['interpretable_score'] for r in rows)
    assert all(r['calibrated_ltr_score'] is not None for r in rows)

def test_unpromoted_model_falls_back(bundle,config):
    bundle['governed_model_registry']['records'][0]['promotion_status']='NOT_PROMOTED'; rehash(bundle['governed_model_registry'])
    result=run_s6_pipeline(bundle,config); rows=result['outputs']['hybrid_candidate_score_panel']['records']
    assert result['outputs']['resolved_runtime_model_reference']['record_count']==0
    assert all(r['hybrid_status']=='INTERPRETABLE_FALLBACK' for r in rows)
    assert all(r['calibrated_ltr_score'] is None for r in rows)

def test_abstain_policy_preserves_candidate_with_null_score(bundle,config):
    bundle['governed_model_registry']['records'][0]['promotion_status']='NOT_PROMOTED'; rehash(bundle['governed_model_registry'])
    config['runtime_policy']['fallback_mode']='ABSTAIN_MODEL_PATH'
    rows=run_s6_pipeline(bundle,config)['outputs']['hybrid_candidate_score_panel']['records']
    assert all(r['hybrid_status']=='ABSTAINED' and r['hybrid_score'] is None for r in rows)

def test_low_confidence_uses_interpretable_fallback(bundle,config):
    bundle['factor_adjusted_candidate_panel']['records'][0]['ood_score']=0.95; rehash(bundle['factor_adjusted_candidate_panel'])
    from tests.learning.tests.s6.conftest import rebuild_tournament_manifest
    rebuild_tournament_manifest(bundle)
    rows=run_s6_pipeline(bundle,config)['outputs']['hybrid_candidate_score_panel']['records']
    target=next(r for r in rows if r['candidate_id']=='cand-01')
    assert target['hybrid_status']=='INTERPRETABLE_FALLBACK'


def test_runtime_compatibility_report_explains_every_model(bundle, config):
    result = run_s6_pipeline(bundle, config)
    report = result['outputs']['runtime_model_compatibility_report']['records'][0]
    assert report['evaluated_model_count'] == len(bundle['ltr_model_artifact']['records'])
    assert len(report['model_decisions']) == report['evaluated_model_count']
    assert all('checks' in row and 'failed_checks' in row for row in report['model_decisions'])


def test_confidence_report_has_component_decomposition(bundle, config):
    result = run_s6_pipeline(bundle, config)
    rows = result['outputs']['ltr_score_confidence_panel']['records']
    assert rows
    assert all(row['aggregation_method'] == 'MIN_AVAILABLE_REQUIRED_COMPONENTS_WITH_COVERAGE_GATE' for row in rows)
    assert all('missing_components' in row and 'component_reason_codes' in row for row in rows)
