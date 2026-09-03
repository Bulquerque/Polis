from __future__ import annotations

from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from quant_pipeline.phase_07_strategy_tournament.tournament.s4_runner import run_subphase
from tests.tournament.tests.s4.factories import execution_config, make_bundle

ROOT = Path(__file__).resolve().parents[3]


def test_all_exported_schemas_are_valid_draft_2020_12():
    schemas = sorted((ROOT / "schemas").glob("*.schema.yaml"))
    assert len(schemas) >= 19
    for path in schemas:
        Draft202012Validator.check_schema(yaml.safe_load(path.read_text(encoding="utf-8")))


def test_input_and_output_fixtures_validate_against_exported_schemas():
    bundle = make_bundle()
    result = run_subphase(bundle, execution_config())
    combined = {**bundle, **result["outputs"]}
    for name, artifact in combined.items():
        path = ROOT / "schemas" / f"{name}.schema.yaml"
        if not path.exists():
            continue
        schema = yaml.safe_load(path.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(artifact)
