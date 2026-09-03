from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]


def test_all_s34_schemas_are_valid_and_hash_bound() -> None:
    manifest = yaml.safe_load((ROOT / "config/research_tools/SCHEMA_BUNDLE_MANIFEST_S34.yaml").read_text())
    assert len(manifest["entries"]) == 18
    for entry in manifest["entries"]:
        path = ROOT / entry["relative_path"]
        schema = json.loads(path.read_text())
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_registry_declares_exactly_five_s34_modules() -> None:
    registry = yaml.safe_load((ROOT / "contracts/extensions/research_tools/MODULE_REGISTRY_S34.yaml").read_text())
    assert [item["module_id"] for item in registry["modules"]] == [f"P3.S34.M{i:02d}" for i in range(1, 6)]
    for item in registry["modules"]:
        assert (ROOT / item["implementation"]).is_file()
        assert (ROOT / item["contract"]).is_file()


def test_s34_code_has_no_network_or_wall_clock_calls() -> None:
    roots = [
        ROOT / "src/quant_pipeline/phase_03_agents_rag_memory/extensions/research_tools/services/capability_taxonomy.py",
        ROOT / "src/quant_pipeline/phase_03_agents_rag_memory/extensions/research_tools/services/person_capabilities.py",
        ROOT / "src/quant_pipeline/phase_03_agents_rag_memory/extensions/research_tools/services/research_plans.py",
        ROOT / "src/quant_pipeline/phase_03_agents_rag_memory/extensions/research_tools/compatibility/s21_entitlements.py",
        ROOT / "src/quant_pipeline/phase_03_agents_rag_memory/extensions/research_tools/compatibility/s20_context.py",
    ]
    forbidden = {"requests", "httpx", "urllib", "aiohttp", "datetime.now", "date.today", "random.random"}
    for path in roots:
        text = path.read_text()
        assert not forbidden.intersection({item for item in forbidden if item in text})
        ast.parse(text)
