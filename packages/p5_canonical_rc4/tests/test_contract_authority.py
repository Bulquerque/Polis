from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from quant_pipeline.phase_05_underlying_forecasts.domain.core import ModuleResult
from quant_pipeline.phase_05_underlying_forecasts.registry import list_modules

from .fixtures import build_fixture

ROOT = Path(__file__).resolve().parents[1]


def _validate(schema_path: Path, value: dict) -> None:
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    validator.validate(value)


def test_p4_reference_schemas_accept_canonical_fixture():
    fixture = build_fixture()
    _validate(
        ROOT / "references/p4_v14_9/phase5_feature_handoff_manifest.schema.yaml",
        fixture["phase5_feature_handoff_manifest"],
    )
    _validate(
        ROOT / "references/p4_v14_9/model_consumer_view_manifest.schema.yaml",
        fixture["model_consumer_view_manifest"],
    )
    _validate(
        ROOT / "references/p4_v14_9/model_consumer_view_bundle.schema.yaml",
        fixture["model_consumer_view_bundle"],
    )


def test_generated_schema_matches_runtime_model():
    generated = json.loads((ROOT / "schemas/ModuleResult.schema.json").read_text(encoding="utf-8"))
    assert generated == ModuleResult.model_json_schema()


def test_generated_module_contracts_match_registry():
    matrix = yaml.safe_load((ROOT / "contracts/MODULE_IO_MATRIX.yaml").read_text(encoding="utf-8"))
    contract_rows = {row["module_id"]: row for row in matrix["modules"]}
    modules = {module.module_id: module for module in list_modules()}
    assert contract_rows.keys() == modules.keys()
    for module_id, module in modules.items():
        row = contract_rows[module_id]
        assert tuple(row["required_inputs"]) == module.required_inputs
        assert tuple(row["optional_inputs"]) == module.optional_inputs
        assert tuple(row["outputs"]) == module.outputs
