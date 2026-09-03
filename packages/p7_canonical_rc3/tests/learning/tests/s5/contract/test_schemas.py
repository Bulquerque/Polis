import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from quant_pipeline.phase_07_strategy_tournament.learning.runner_s5 import run_s5_pipeline

ROOT = Path(__file__).resolve().parents[3]


def _validate(name, artifact):
    schema_path = ROOT / "schemas" / f"{name}.schema.json"
    assert schema_path.exists(), name
    schema = json.loads(schema_path.read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(artifact)


def test_all_inputs_validate_against_schemas(input_bundle):
    for name, artifact in input_bundle.items():
        _validate(name, artifact)


def test_all_outputs_validate_against_schemas(input_bundle, config):
    result = run_s5_pipeline(input_bundle, config)
    for name, artifact in result["outputs"].items():
        _validate(name, artifact)
