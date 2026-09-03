from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import yaml

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S29_M01_agent_disagreement_panel_builder import (
    run_module as run_m01,
)
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S29_M02_evidence_claim_extractor import (
    run_module as run_m02,
)


ROOT = Path(__file__).resolve().parents[2]


def test_all_yaml_and_json_files_parse() -> None:
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix in {".yaml", ".yml"}:
            yaml.safe_load(path.read_text(encoding="utf-8"))
        elif path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))


def test_all_s29_json_schemas_are_valid_draft_2020_12() -> None:
    for path in (ROOT / "schemas" / "products" / "s29").glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        Draft202012Validator.check_schema(schema)


def test_output_fixtures_validate_semantic_schemas(
    m01_inputs: dict,
    m02_inputs: dict,
    execution_context: dict,
) -> None:
    outputs = {
        "agent_disagreement_panel.semantic.schema.json": run_m01(
            m01_inputs, execution_context
        )["outputs"]["agent_disagreement_panel"],
        "evidence_tag_panel.semantic.schema.json": run_m02(m02_inputs, execution_context)[
            "outputs"
        ]["evidence_tag_panel"],
    }
    for schema_name, output in outputs.items():
        schema = json.loads((ROOT / "schemas" / "products" / "s29" / schema_name).read_text())
        Draft202012Validator(schema).validate(output)


def test_external_schema_hash_manifest_matches_local_authority() -> None:
    manifest = yaml.safe_load(
        (ROOT / "contracts" / "products" / "S29_EXTERNAL_SCHEMA_HASHES.yaml").read_text()
    )
    for row in manifest["schemas"]:
        path = ROOT / "schemas" / row["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]


def test_module_contracts_match_implementation_targets() -> None:
    for name in (
        "P3_S29_M01_agent_disagreement_panel_builder.yaml",
        "P3_S29_M02_evidence_claim_extractor.yaml",
    ):
        contract = yaml.safe_load((ROOT / "modules" / name).read_text())
        assert contract["subphase"] == "P3.S29"
        assert contract["status"] == "implemented_qualified_internal"
        assert (ROOT / contract["implementation_target"]).is_file()
        assert (ROOT / contract["unit_test_target"]).is_file()
        assert (ROOT / contract["integration_test_target"]).is_file()
