from pathlib import Path
import json, yaml

ROOT=Path(__file__).resolve().parents[5]

def test_all_company_schemas_are_valid_json():
    files=sorted((ROOT/"contracts/extensions/research_tools/schemas/families/company").glob("*.json"))
    assert len(files) == 17
    for path in files:
        data=json.loads(path.read_text())
        assert data["$schema"].endswith("2020-12/schema")

def test_all_s38_module_contracts_have_owner_prompt():
    files=sorted((ROOT/"contracts/extensions/research_tools/modules").glob("P3_S38_M*.yaml"))
    assert len(files) == 6
    for path in files:
        data=yaml.safe_load(path.read_text())
        assert data["owner_prompt"].endswith("P3_S38_company_fundamentals_tool_suite.md")
