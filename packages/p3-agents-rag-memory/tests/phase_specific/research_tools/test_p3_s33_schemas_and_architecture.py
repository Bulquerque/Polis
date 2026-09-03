from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from .support import ROOT, load_yaml


def test_all_s33_schemas_are_valid_and_hash_bound():
    manifest = load_yaml("config/research_tools/SCHEMA_BUNDLE_MANIFEST_S33.yaml")
    assert len(manifest["entries"]) == 20
    for entry in manifest["entries"]:
        path = ROOT / entry["relative_path"]
        raw = path.read_bytes()
        schema = json.loads(raw)
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
        assert len(raw) == entry["size_bytes"]


def test_s33_module_registry_is_isolated_from_legacy_registry():
    registry = load_yaml("contracts/extensions/research_tools/MODULE_REGISTRY_S33.yaml")
    assert [item["module_id"] for item in registry["modules"]] == [
        "P3.S33.M01", "P3.S33.M02", "P3.S33.M03", "P3.S33.M04", "P3.S33.M05"
    ]
    legacy = load_yaml("contracts/MODULE_REGISTRY.yaml")
    assert all(not str(item.get("module_id", "")).startswith("P3.S33") for item in legacy.get("modules", []))


def test_s33_imports_no_network_clients_and_no_old_wrappers():
    source_root = ROOT / "src/quant_pipeline/phase_03_agents_rag_memory/extensions/research_tools"
    forbidden = ("requests", "httpx", "aiohttp", "urllib.request")
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(any(token in name for token in forbidden) for name in names), path


def test_s33_source_has_no_wall_clock_or_generic_utility_dump():
    source_root = ROOT / "src/quant_pipeline/phase_03_agents_rag_memory/extensions/research_tools"
    names = {path.name for path in source_root.rglob("*.py")}
    assert not names.intersection({"utils.py", "helpers.py", "misc.py", "common.py"})
    for path in source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "datetime.now(" not in text
        assert "date.today(" not in text
