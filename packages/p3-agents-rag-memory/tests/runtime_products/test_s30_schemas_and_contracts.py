from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import yaml

from quant_pipeline.phase_03_agents_rag_memory import s30_models

ROOT = Path(__file__).resolve().parents[2]


def test_all_semantic_schemas_are_valid_draft_2020_12():
    files = sorted((ROOT / "schemas" / "products" / "s30").glob("*.json"))
    assert len(files) == 14
    for path in files:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_models_generate_schemas_with_required_and_extra_forbid():
    schema = s30_models.SocialFeaturePanel.model_json_schema()
    assert "required" in schema
    assert schema["additionalProperties"] is False
    record = schema["$defs"]["SocialFeatureRecord"]
    assert record["additionalProperties"] is False
    assert "social_feature_id" in record["required"]


def test_external_schema_hashes_are_exact():
    manifest = yaml.safe_load((ROOT / "contracts" / "products" / "S30_EXTERNAL_SCHEMA_HASHES.yaml").read_text())
    assert manifest["schema_count"] == 6
    for row in manifest["schemas"]:
        reference = ROOT / "schemas" / row["file"]
        authority = ROOT / "schemas" / row["file"]
        path = reference if reference.is_file() else authority
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
        assert path.read_bytes() == authority.read_bytes()


def test_module_contracts_remain_canonical_and_implemented():
    for index, name in enumerate((
        "social_feature_builder",
        "context_memory_feature_builder",
        "hypothesis_registry_builder",
        "phase4_social_handoff_builder",
        "variable_evolution_handoff_builder",
    ), start=1):
        path = ROOT / "modules" / f"P3_S30_M{index:02d}_{name}.yaml"
        contract = yaml.safe_load(path.read_text())
        assert contract["module_id"] == f"P3.S30.M{index:02d}"
        assert contract["status"] == "implemented_qualified_internal"
        assert contract["implementation_status_policy"]["current"] == "IMPLEMENTED_QUALIFIED_INTERNAL"


def test_legacy_social_rows_are_accepted_by_declared_required_fields(s30_products):
    schema = yaml.safe_load((ROOT / "schemas" / "social_feature_panel.schema.yaml").read_text())
    required = set(schema["required_fields"])
    assert all(required <= set(row) for row in s30_products["social_feature_panel"]["records"])


def test_hypothesis_rows_are_legacy_compatible(s30_products):
    schema = yaml.safe_load((ROOT / "schemas" / "hypothesis_registry.schema.yaml").read_text())
    required = set(schema["required_fields"])
    assert all(required <= set(row) for row in s30_products["hypothesis_registry"]["records"])
