from pathlib import Path
import json
from jsonschema import Draft202012Validator, FormatChecker
from quant_pipeline.phase_07_strategy_tournament.learning.runner_s6 import run_s6_pipeline

ROOT=Path(__file__).resolve().parents[3]
def validate(name,artifact):
    schema=json.loads((ROOT/f'schemas/{name}.schema.json').read_text())
    Draft202012Validator(schema,format_checker=FormatChecker()).validate(artifact)

def test_all_fixture_inputs_validate(bundle):
    for name,artifact in bundle.items(): validate(name,artifact)

def test_all_runtime_outputs_validate(bundle,config):
    for name,artifact in run_s6_pipeline(bundle,config)['outputs'].items(): validate(name,artifact)
