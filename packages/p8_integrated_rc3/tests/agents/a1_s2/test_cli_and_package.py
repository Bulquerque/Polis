
import json
import subprocess
import sys
import os
from pathlib import Path

from quant_pipeline.phase_08_portfolio_control.s02_candidate_context import P8CandidateContextBundleV1
from tests.agents.a1_s2.factories import build_input


def test_public_surface_imports():
    import quant_pipeline.phase_08_portfolio_control.s02_candidate_context as pkg
    assert pkg.P8CandidateContextBundleV1 is P8CandidateContextBundleV1


def test_namespace_package_has_no_quant_pipeline_init():
    root=Path(__file__).resolve().parents[1]
    assert not (root/"src/quant_pipeline/__init__.py").exists()


def test_cli_executes_sealed_bundle(tmp_path: Path):
    bundle,context=build_input()
    input_path=tmp_path/"input.json";output_path=tmp_path/"output.json"
    input_path.write_text(bundle.model_dump_json())
    env=os.environ.copy()
    root=Path(__file__).resolve().parents[1]
    env["PYTHONPATH"]=str(root/"src") + os.pathsep + env.get("PYTHONPATH","")
    proc=subprocess.run([sys.executable,"-m","quant_pipeline.phase_08_portfolio_control.s02_candidate_context.cli",
        str(input_path),str(output_path),"--computed-at",context.computed_at.isoformat()],capture_output=True,text=True,check=True,env=env)
    assert json.loads(proc.stdout)["status"]=="PASS"
    parsed=P8CandidateContextBundleV1.model_validate_json(output_path.read_bytes(),strict=True)
    assert parsed.snapshot_id==bundle.snapshot.snapshot_id


def test_cli_main_direct(monkeypatch, tmp_path: Path, capsys):
    from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.cli import main
    bundle,context=build_input()
    input_path=tmp_path/"direct-input.json";output_path=tmp_path/"direct-output.json"
    input_path.write_text(bundle.model_dump_json())
    monkeypatch.setattr(sys,"argv",["p8-s2",str(input_path),str(output_path),"--computed-at",context.computed_at.isoformat()])
    assert main()==0
    assert json.loads(capsys.readouterr().out)["status"]=="PASS"
    assert output_path.exists()
