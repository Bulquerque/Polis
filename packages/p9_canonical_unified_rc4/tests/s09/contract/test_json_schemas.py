from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]


def _load_json(relative_path: str) -> object:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_all_generated_schemas_are_valid_draft_2020_12() -> None:
    schema_files = sorted((ROOT / "schemas" / "s09").glob("*.schema.json"))
    assert schema_files
    for path in schema_files:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_input_fixture_matches_promotion_evidence_schema() -> None:
    schema = _load_json("schemas/s09/promotion_evidence_input_bundle.schema.json")
    fixture = _load_json("fixtures/s09/input/p9_s9_promotion_evidence_input_sample.json")
    Draft202012Validator(schema).validate(fixture)


def test_output_fixture_matches_execution_envelope_schema() -> None:
    schema = _load_json("schemas/s09/s9_execution_envelope.schema.json")
    fixture = _load_json("fixtures/s09/output/p9_s9_execution_envelope_sample.json")
    Draft202012Validator(schema).validate(fixture)


def test_input_fixture_round_trips_through_strict_pydantic_json_parser() -> None:
    from quant_pipeline.phase_09.subphases.s09_competition_promotion.models import (
        PromotionEvidenceInputBundle,
    )

    raw = (ROOT / "fixtures/s09/input/p9_s9_promotion_evidence_input_sample.json").read_text(
        encoding="utf-8"
    )
    parsed = PromotionEvidenceInputBundle.model_validate_json(raw)
    assert parsed.champion_configuration_id == "champion"
    assert len(parsed.configurations) == 4
