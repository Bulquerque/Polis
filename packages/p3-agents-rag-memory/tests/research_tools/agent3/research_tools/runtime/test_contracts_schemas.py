from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[5]


def test_all_s40_module_contracts_have_owner_prompt_and_existing_targets():
    contracts = sorted((ROOT / "contracts/extensions/research_tools/modules").glob("P3_S40_*.yaml"))
    assert len(contracts) == 8
    for path in contracts:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["owner_prompt"] == "extensions/research_tools/subphases/P3_S40_runtime_evidence_qualification_downstream.md"
        assert (ROOT / data["implementation_target"]).is_file()
        assert data["inputs"]
        assert data["outputs"]


def test_runtime_schemas_are_valid_json_schema_documents():
    schemas = sorted((ROOT / "contracts/extensions/research_tools/schemas/families/runtime").glob("*.schema.json"))
    assert len(schemas) == 31
    for path in schemas:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert data["type"] == "object"
        assert data.get("additionalProperties") is False


def test_s40_overlay_has_exactly_eight_unique_modules():
    data = yaml.safe_load((ROOT / "contracts/extensions/research_tools/P3_S40_MODULE_IO_OVERLAY.yaml").read_text())
    ids = [item["module_id"] for item in data["module_io_overlay"]]
    assert ids == [f"P3.S40.M{index:02d}" for index in range(1, 9)]
    assert len(ids) == len(set(ids))
