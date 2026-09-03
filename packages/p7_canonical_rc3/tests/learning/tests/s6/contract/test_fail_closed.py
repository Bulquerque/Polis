import pytest
from quant_pipeline.phase_07_strategy_tournament.learning.runner_s6 import run_s6_pipeline
from quant_pipeline.phase_07_strategy_tournament.learning.domain.errors import P7S6Error
from tests.learning.tests.s6.conftest import rehash,rebuild_tournament_manifest

def test_manifest_hash_mismatch_rejected(bundle,config):
    bundle['interpretable_tournament_handoff_manifest']['records'][0]['content_sha256']='0'*64;rehash(bundle['interpretable_tournament_handoff_manifest'])
    with pytest.raises(P7S6Error) as exc: run_s6_pipeline(bundle,config)
    assert exc.value.issue.code=='P7_LTR_TOURNAMENT_HANDOFF_INVALID'

def test_candidate_set_mismatch_rejected(bundle,config):
    bundle['candidate_lineage_panel']['records'].pop();rehash(bundle['candidate_lineage_panel']);rebuild_tournament_manifest(bundle)
    with pytest.raises(P7S6Error) as exc: run_s6_pipeline(bundle,config)
    assert exc.value.issue.code=='P7_LTR_RUNTIME_CANDIDATE_RECONCILIATION_FAILED'

def test_metric_scale_mismatch_rejected(bundle,config):
    bundle['metric_semantics_registry']['records'][0]['scale_id']='incompatible';rehash(bundle['metric_semantics_registry']);rebuild_tournament_manifest(bundle)
    with pytest.raises(P7S6Error) as exc: run_s6_pipeline(bundle,config)
    assert exc.value.issue.code=='P7_LTR_SCORE_SCALE_MISMATCH'

def test_model_record_hash_mismatch_rejected(bundle,config):
    bundle['ltr_model_artifact']['records'][0]['model_state']['intercept']=999.0;rehash(bundle['ltr_model_artifact'])
    with pytest.raises(P7S6Error) as exc: run_s6_pipeline(bundle,config)
    assert exc.value.issue.code=='P7_LTR_RUNTIME_MODEL_HASH_MISMATCH'

def test_invalid_model_state_rejected(bundle,config):
    model=bundle['ltr_model_artifact']['records'][0]
    old=model['model_hash']; model['model_state']['feature_scales']=[1.0]
    from quant_pipeline.phase_07_strategy_tournament.learning.domain.canonical import digest
    payload=dict(model);payload.pop('model_hash');model['model_hash']=digest(payload);rehash(bundle['ltr_model_artifact'])
    for row in bundle['ltr_model_qualification_registry']['records']:
        if row['model_hash']==old: row['model_hash']=model['model_hash']
    rehash(bundle['ltr_model_qualification_registry'])
    bundle['governed_model_registry']['records'][0]['model_hash']=model['model_hash'];rehash(bundle['governed_model_registry'])
    for row in bundle['ltr_model_qualification_report']['records']:
        if row['model_hash']==old: row['model_hash']=model['model_hash']
    rehash(bundle['ltr_model_qualification_report'])
    with pytest.raises(P7S6Error) as exc: run_s6_pipeline(bundle,config)
    assert exc.value.issue.code=='P7_LTR_RUNTIME_MODEL_STATE_INVALID'

def test_qualification_evidence_must_close(bundle,config):
    bundle['ltr_model_qualification_report']['records'][0]['gate_results']['deterministic']=False
    rehash(bundle['ltr_model_qualification_report'])
    with pytest.raises(P7S6Error) as exc: run_s6_pipeline(bundle,config)
    assert exc.value.issue.code=='P7_LTR_RUNTIME_QUALIFICATION_EVIDENCE_INVALID'
