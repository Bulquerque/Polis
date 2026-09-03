from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from .support import ROOT, load_yaml


def test_all_generated_schemas_are_valid_draft_2020_12():
    manifest = load_yaml("config/research_tools/SCHEMA_BUNDLE_MANIFEST.yaml")
    assert len(manifest["entries"]) == 86
    for entry in manifest["entries"]:
        schema = json.loads((ROOT / entry["relative_path"]).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_generated_manifest_hashes_match_files():
    import hashlib
    manifest = load_yaml("config/research_tools/SCHEMA_BUNDLE_MANIFEST.yaml")
    for entry in manifest["entries"]:
        raw = (ROOT / entry["relative_path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
        assert len(raw) == entry["size_bytes"]
