from copy import deepcopy
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "quant_pipeline.phase_00_zero_trust_guardian"

sys.path.insert(0, str(ROOT / "src"))

runner = import_module(f"{PACKAGE}.runner")


def _row(**changes):
    value = {
        "module_id": "P0.S1.M01",
        "module_name": "example_module",
        "subphase": "P0.S1",
        "consumes_from": {
            "modules": [],
            "artifacts": ["seed"],
            "phase_inputs": ["seed"],
        },
        "emits_to": {
            "modules": [],
            "artifacts": ["artifact"],
            "phase_outputs": ["artifact"],
        },
        "module_contract": "modules/P0_S1_M01_example_module.yaml",
    }
    value.update(changes)
    return value


def _contract(**changes):
    value = {
        "module_id": "P0.S1.M01",
        "module_name": "example_module",
        "phase": "P0",
        "subphase": "P0.S1",
        "inputs": ["seed"],
        "outputs": ["artifact"],
    }
    value.update(changes)
    return value


def _result(**changes):
    value = {
        "module_id": "P0.S1.M01",
        "module_name": "example_module",
        "phase": "P0",
        "subphase": "P0.S1",
        "contract": "P0_S1_M01_example_module.yaml",
        "required_inputs": ["seed"],
        "outputs": {"artifact": {"artifact_id": "a-1"}},
    }
    value.update(changes)
    return value


def _write_yaml(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def _isolated_runner(monkeypatch, tmp_path, module_result=None, *, required_inputs=None):
    contract_root = tmp_path / "contracts"
    module_root = tmp_path / "modules"
    schema_root = tmp_path / "schemas"
    required_inputs = required_inputs or ["seed"]
    _write_yaml(
        contract_root / "INPUT_CONTRACTS.yaml",
        {
            "phase": "phase_00_zero_trust_guardian",
            "required_inputs": required_inputs,
            "forbidden_inputs": ["forbidden_input"],
        },
    )
    _write_yaml(
        contract_root / "OUTPUT_CONTRACTS.yaml",
        {
            "outputs": ["artifact"],
            "forbidden_output_fields": ["secret"],
        },
    )
    _write_yaml(contract_root / "MODULE_IO_MATRIX.yaml", {"module_io_matrix": [_row()]})
    _write_yaml(module_root / "P0_S1_M01_example_module.yaml", _contract())
    _write_yaml(
        schema_root / "artifact.schema.yaml",
        {
            "schema_id": "artifact.v1",
            "artifact_name": "artifact",
            "required_fields": ["artifact_id"],
            "forbidden_fields": ["secret"],
        },
    )
    monkeypatch.setattr(runner, "CONTRACT_ROOT", contract_root)
    monkeypatch.setattr(runner, "MODULE_ROOT", module_root)
    monkeypatch.setattr(runner, "SCHEMA_ROOT", schema_root)
    result = deepcopy(module_result if module_result is not None else _result())
    monkeypatch.setattr(
        runner,
        "import_module",
        lambda _name: SimpleNamespace(run_module=lambda _inputs, _config: deepcopy(result)),
    )
    return contract_root


def test_isolated_runner_accepts_only_the_declared_contract(monkeypatch, tmp_path):
    _isolated_runner(monkeypatch, tmp_path)

    result = runner.run_phase({"seed": {"value": 1}}, {})

    assert result["phase_outputs"] == {"artifact": {"artifact_id": "a-1"}}
    assert [item["module_id"] for item in result["module_results"]] == ["P0.S1.M01"]


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("module_id", "P0.S1.M99"),
        ("module_name", "other_module"),
        ("phase", "P1"),
        ("subphase", "P0.S9"),
        ("contract", "other.yaml"),
    ],
)
def test_runner_rejects_tampered_result_identity(monkeypatch, tmp_path, field, tampered):
    bad_result = _result(**{field: tampered})
    _isolated_runner(monkeypatch, tmp_path, bad_result)

    with pytest.raises(ValueError, match=rf"result {field} mismatch"):
        runner.run_phase({"seed": 1}, {})


@pytest.mark.parametrize(
    "outputs",
    [
        {},
        {"artifact": {"artifact_id": "a-1"}, "undeclared": {}},
        {"undeclared": {}},
    ],
)
def test_runner_requires_exactly_the_matrix_outputs(monkeypatch, tmp_path, outputs):
    _isolated_runner(monkeypatch, tmp_path, _result(outputs=outputs))

    with pytest.raises(ValueError, match="outputs mismatch"):
        runner.run_phase({"seed": 1}, {})


def test_runner_rejects_any_existing_artifact_overwrite(monkeypatch, tmp_path):
    _isolated_runner(monkeypatch, tmp_path, required_inputs=["seed", "artifact"])

    with pytest.raises(ValueError, match="attempted to overwrite existing artifacts"):
        runner.run_phase({"seed": 1, "artifact": {"artifact_id": "original"}}, {})


def test_topology_rejects_unknown_and_unexecuted_dependencies():
    dependent = _row(
        module_id="P0.S1.M02",
        consumes_from={
            "modules": ["P0.S1.M01"],
            "artifacts": ["seed"],
            "phase_inputs": ["seed"],
        },
    )

    with pytest.raises(ValueError, match="unknown module dependencies"):
        runner._topological_order([dependent])

    with pytest.raises(ValueError, match="dependencies were not executed"):
        runner._assert_dependencies_executed(dependent, set())

    runner._assert_dependencies_executed(dependent, {"P0.S1.M01"})


def test_contract_outputs_must_match_matrix_exactly():
    with pytest.raises(ValueError, match="contract outputs do not match"):
        runner._validate_contract_against_matrix(
            _contract(outputs=["artifact", "undeclared"]),
            _row(),
        )


def test_schema_rejects_missing_and_nested_forbidden_fields(monkeypatch, tmp_path):
    schema_root = tmp_path / "schemas"
    _write_yaml(
        schema_root / "artifact.schema.yaml",
        {
            "artifact_name": "artifact",
            "required_fields": ["artifact_id"],
            "forbidden_fields": ["secret"],
        },
    )
    monkeypatch.setattr(runner, "SCHEMA_ROOT", schema_root)

    with pytest.raises(ValueError, match="missing required fields"):
        runner._validate_artifact("artifact", {})
    with pytest.raises(ValueError, match="contains forbidden fields"):
        runner._validate_artifact(
            "artifact",
            {"artifact_id": "a-1", "nested": [{"secret": "leak"}]},
        )


def test_schema_enforces_declared_types_and_structure(monkeypatch, tmp_path):
    schema_root = tmp_path / "schemas"
    _write_yaml(
        schema_root / "artifact.schema.yaml",
        {
            "artifact_name": "artifact",
            "required_fields": ["artifact_id", "payload"],
            "forbidden_fields": [],
            "type": "object",
            "field_types": {"artifact_id": "string"},
            "properties": {
                "artifact_id": {"type": "string", "minLength": 1},
                "payload": {
                    "type": "object",
                    "required": ["items"],
                    "additionalProperties": False,
                    "properties": {
                        "items": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "integer"},
                        }
                    },
                },
            },
        },
    )
    monkeypatch.setattr(runner, "SCHEMA_ROOT", schema_root)
    runner._validate_artifact("artifact", {"artifact_id": "a-1", "payload": {"items": [1]}})

    with pytest.raises(ValueError, match="schema type 'integer'"):
        runner._validate_artifact(
            "artifact",
            {"artifact_id": "a-1", "payload": {"items": [True]}},
        )
    with pytest.raises(ValueError, match="undeclared structured fields"):
        runner._validate_artifact(
            "artifact",
            {"artifact_id": "a-1", "payload": {"items": [1], "extra": 2}},
        )
