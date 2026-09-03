import json, os, subprocess, sys
from pathlib import Path
import pytest
from quant_pipeline.phase_07_strategy_tournament.learning import run_s6_pipeline
from quant_pipeline.phase_07_strategy_tournament.learning.boundary import ArtifactEnvelope, parse_artifact
from quant_pipeline.phase_07_strategy_tournament.learning.domain.canonical import canonical_json, parse_utc
from quant_pipeline.phase_07_strategy_tournament.learning.domain.errors import P7S6Error
from quant_pipeline.phase_07_strategy_tournament.learning.adapters.runtime_ranker_resolver import resolve_ranker

ROOT=Path(__file__).resolve().parents[3]

def test_public_api(bundle,config):
    assert run_s6_pipeline(bundle,config)['status']=='PASS'

def test_cli_entrypoint(tmp_path):
    out=tmp_path/'out.json'
    cmd=[sys.executable,'-m','quant_pipeline.phase_07_strategy_tournament.learning.runner_s6','--input',str(ROOT/'fixtures/integration/s6_input_bundle.json'),'--config',str(ROOT/'configs/s6_default_config.yaml'),'--output',str(out)]
    env = os.environ.copy(); env['PYTHONPATH'] = str(ROOT.parents[1] / 'src')
    subprocess.run(cmd,cwd=ROOT,check=True,env=env)
    assert json.loads(out.read_text())['status']=='PASS'

def test_unsupported_adapter_is_fail_closed():
    with pytest.raises(P7S6Error) as exc: resolve_ranker('unknown')
    assert exc.value.issue.code=='P7_LTR_RUNTIME_IMPLEMENTATION_UNSUPPORTED'

def test_canonical_rejects_non_finite():
    with pytest.raises(P7S6Error): canonical_json({'x':float('nan')})

def test_parse_utc_rejects_naive_and_non_string():
    with pytest.raises(P7S6Error): parse_utc('2025-01-01T00:00:00',field='x')
    with pytest.raises(P7S6Error): parse_utc(1,field='x')

def test_artifact_count_and_hash_are_verified(bundle):
    raw=dict(bundle['factor_adjusted_candidate_panel']);raw['record_count']=999
    artifact=ArtifactEnvelope.model_validate(raw)
    with pytest.raises(P7S6Error): artifact.verify()
    raw=dict(bundle['factor_adjusted_candidate_panel']);raw['content_sha256']='0'*64
    artifact=ArtifactEnvelope.model_validate(raw)
    with pytest.raises(P7S6Error): artifact.verify()
    with pytest.raises(P7S6Error): parse_artifact([],name='factor_adjusted_candidate_panel')

def test_main_function(monkeypatch,tmp_path):
    from quant_pipeline.phase_07_strategy_tournament.learning import runner_s6
    out=tmp_path/'main.json'
    monkeypatch.setattr(sys,'argv',['runner_s6','--input',str(ROOT/'fixtures/integration/s6_input_bundle.json'),'--config',str(ROOT/'configs/s6_default_config.yaml'),'--output',str(out)])
    runner_s6.main()
    assert json.loads(out.read_text())['subphase_id']=='P7.S6'

def test_boundary_invalid_context_and_artifact_name(bundle):
    from quant_pipeline.phase_07_strategy_tournament.learning.boundary import parse_context
    with pytest.raises(P7S6Error): parse_context({})
    with pytest.raises(P7S6Error): parse_context({'context':{'run_id':'x'}})
    with pytest.raises(P7S6Error): parse_artifact(bundle['factor_adjusted_candidate_panel'],name='wrong_name')
