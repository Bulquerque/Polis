import json
from pathlib import Path
from jsonschema import Draft202012Validator
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.cli import main
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.schema_export import SCHEMAS,export_schemas

def test_exported_schemas_are_valid(tmp_path):
    paths=export_schemas(tmp_path)
    assert len(paths)==len(SCHEMAS)==10
    for path in paths: Draft202012Validator.check_schema(json.loads(path.read_text()))

def test_cli_export(tmp_path):
    assert main(['export-schemas',str(tmp_path)])==0
    assert (tmp_path/'audit_release_request.schema.json').exists()

def test_cli_audit(tmp_path,bundle):
    inp=tmp_path/'in.json'; out=tmp_path/'out.json'; inp.write_text(bundle.model_dump_json(),encoding='utf-8')
    assert main(['audit',str(inp),'--output',str(out)])==0
    assert json.loads(out.read_text())['overall_status']=='PASS'

def test_cli_run(tmp_path,orchestration_request):
    inp=tmp_path/'in.json'; out=tmp_path/'out.json'; inp.write_text(orchestration_request.model_dump_json(),encoding='utf-8')
    assert main(['run',str(inp),'--output',str(out)])==0
    assert json.loads(out.read_text())['p9_handoff']['production_promotion_allowed'] is False
