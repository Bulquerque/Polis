from copy import deepcopy
from quant_pipeline.phase_07_strategy_tournament.learning.runner_s6 import run_s6_pipeline
from tests.learning.tests.s6.conftest import rehash,rebuild_tournament_manifest

def mapping(result,name,field): return {(r['comparison_group_id'],r['candidate_id']):r[field] for r in result['outputs'][name]['records']}

def test_candidate_permutation_invariance(bundle,config):
    baseline=run_s6_pipeline(deepcopy(bundle),deepcopy(config))
    for name in ['factor_adjusted_candidate_panel','pareto_candidate_panel','interpretable_score_panel','interpretable_score_decomposition_panel','candidate_lineage_panel']:
        bundle[name]['records'].reverse();rehash(bundle[name])
    rebuild_tournament_manifest(bundle)
    permuted=run_s6_pipeline(bundle,config)
    assert mapping(baseline,'ltr_model_score_panel','raw_ltr_score')==mapping(permuted,'ltr_model_score_panel','raw_ltr_score')
    assert mapping(baseline,'hybrid_candidate_score_panel','hybrid_score')==mapping(permuted,'hybrid_candidate_score_panel','hybrid_score')

def test_replay_hashes_are_deterministic(bundle,config):
    first=run_s6_pipeline(deepcopy(bundle),deepcopy(config));second=run_s6_pipeline(deepcopy(bundle),deepcopy(config))
    assert {k:v['content_sha256'] for k,v in first['outputs'].items()}=={k:v['content_sha256'] for k,v in second['outputs'].items()}

def test_confidence_shrinks_ltr_weight(bundle,config):
    result=run_s6_pipeline(bundle,config)
    for row in result['outputs']['hybrid_score_decomposition_panel']['records']:
        assert row['effective_ltr_weight']<=config['blend_policy']['ltr_weight']
        assert abs(row['effective_interpretable_weight']+row['effective_ltr_weight']-1.0)<1e-12
        assert row['safety_penalty_applied'] is False
