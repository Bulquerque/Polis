import json
from pathlib import Path

from jsonschema import Draft202012Validator

from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.cli import main
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.schema_export import SCHEMA_MODELS, export_schemas


def test_schemas_are_draft_2020_12(tmp_path):
    paths = export_schemas(tmp_path)
    assert len(paths) == len(SCHEMA_MODELS)
    for path in paths:
        schema = json.loads(path.read_text())
        assert schema["$schema"].endswith("2020-12/schema")
        Draft202012Validator.check_schema(schema)


def test_request_schema_rejects_extra(tmp_path, fixture_payload):
    export_schemas(tmp_path)
    schema = json.loads((tmp_path / "runtime_assurance_request.schema.json").read_text())
    fixture_payload["extra"] = 1
    errors = list(Draft202012Validator(schema).iter_errors(fixture_payload))
    assert errors


def test_cli_validate(root_dir=Path(__file__).parents[1]):
    assert main(["validate-request", str(root_dir / "subphases/s09/fixtures/input/normal_request.json")]) == 0


def test_cli_run(tmp_path, root_dir=Path(__file__).parents[1]):
    output = tmp_path / "result.json"
    assert main(["run", str(root_dir / "subphases/s09/fixtures/input/normal_request.json"), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["runtime_mode"] == "NORMAL"


def test_cli_export(tmp_path):
    assert main(["export-schemas", str(tmp_path)]) == 0
    assert (tmp_path / "runtime_assurance_request.schema.json").exists()


def test_cli_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    assert main(["validate-request", str(bad)]) == 2


def test_namespace_package_has_no_quant_pipeline_init(root_dir=Path(__file__).parents[1]):
    assert not (root_dir / "src/quant_pipeline/__init__.py").exists()
