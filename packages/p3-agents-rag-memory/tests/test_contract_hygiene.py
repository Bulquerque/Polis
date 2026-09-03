from __future__ import annotations
import json,yaml
from jsonschema import Draft202012Validator

def test_all_yaml_and_json_parse(root):
    for p in root.rglob('*'):
        if not p.is_file(): continue
        if any(part in {'.venv','dist','build','__pycache__','.pytest_cache'} for part in p.parts): continue
        if p.suffix in {'.yaml','.yml'}: yaml.safe_load(p.read_text(encoding='utf-8'))
        elif p.suffix=='.json': json.loads(p.read_text(encoding='utf-8'))

def test_33_module_contracts_match_registry(root):
    registry=yaml.safe_load((root/'contracts/MODULE_REGISTRY.yaml').read_text())
    contracts=list((root/'contracts/modules').glob('*.yaml'))
    assert len(contracts)==registry['module_count']==81
    ids={yaml.safe_load(p.read_text())['module_id'] for p in contracts}
    assert ids=={x['module_id'] for x in registry['modules']}

def test_canonical_json_schemas_are_valid(root):
    schemas=list(root.glob('schemas/**/*.json'))
    assert len(schemas)>=3
    for p in schemas: Draft202012Validator.check_schema(json.loads(p.read_text()))

def test_no_nested_archives(root):
    forbidden=[p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in {'.zip','.whl','.tar','.gz'}]
    assert forbidden==[]
