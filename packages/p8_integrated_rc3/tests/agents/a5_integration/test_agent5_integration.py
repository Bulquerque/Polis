from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
import pytest
from pydantic import ValidationError
from quant_pipeline.phase_08_portfolio_control.agent5_integration import Agent5IntegratedRequest, run_agent5_integrated, runtime_evidence_to_s10_ref

def load_request() -> Agent5IntegratedRequest:
    path=Path(__file__).parents[1]/"fixtures/integration/input/normal_request.json"
    return Agent5IntegratedRequest.model_validate_json(path.read_text(encoding="utf-8"))

def test_integrated_flow_links_s9_to_s10():
    result=run_agent5_integrated(load_request())
    assert result.runtime_evidence_ref.producer_module == "P8.S9.M05"
    assert result.audit_release_result.p9_handoff.runtime_evidence_ref == result.runtime_evidence_ref
    assert result.runtime_result.evidence_bundle.production_promotion_allowed is False
    assert result.audit_release_result.p9_handoff.production_promotion_allowed is False

def test_bridge_is_deterministic():
    result=run_agent5_integrated(load_request())
    assert runtime_evidence_to_s10_ref(result.runtime_result.evidence_bundle) == result.runtime_evidence_ref
    assert run_agent5_integrated(load_request()).model_dump_json() == result.model_dump_json()

def test_context_mismatch_is_rejected():
    payload=json.loads((Path(__file__).parents[1]/"fixtures/integration/input/normal_request.json").read_text())
    payload["audit_request"]["stateful_evidence"]["context"]["cycle_id"]="other"
    with pytest.raises(ValidationError): Agent5IntegratedRequest.model_validate_json(json.dumps(payload))

def test_cli(tmp_path: Path):
    inp=Path(__file__).parents[1]/"fixtures/integration/input/normal_request.json"; out=tmp_path/"result.json"
    env=dict(os.environ); env["PYTHONPATH"]=str(Path(__file__).parents[3]/"src")
    subprocess.run([sys.executable,"-m","quant_pipeline.phase_08_portfolio_control.agent5_integration.cli",str(inp),str(out)],check=True,env=env)
    payload=json.loads(out.read_text()); assert payload["runtime_evidence_ref"]["producer_module"] == "P8.S9.M05"

def test_namespace_has_no_root_init():
    root=Path(__file__).parents[1]/"src/quant_pipeline"
    assert not (root/"__init__.py").exists()
