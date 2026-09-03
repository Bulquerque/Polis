"""Phase runner.

Executes module wrappers in contract order and returns the evolved context plus a
summary of declared phase outputs.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
import json
import re
from typing import Any

import yaml

from . import fail_fast
from .validators import normalize_field_name
from .modules._canonical_schema_validator import validate_schema_value as canonical_validate_schema_value

PHASE_NAME = "phase_00_zero_trust_guardian"
PACKAGE_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ROOT = PACKAGE_ROOT / "contracts"
MODULE_ROOT = PACKAGE_ROOT / "modules"
SCHEMA_ROOT = PACKAGE_ROOT / "schemas"


def _load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    fail_fast(isinstance(data, dict), f"{path.name} must be a YAML mapping")
    return data


def _module_path(contract_filename: str) -> str:
    return f"quant_pipeline.{PHASE_NAME}.modules.{Path(contract_filename).stem}"


def _string_list(value: Any, label: str) -> list[str]:
    fail_fast(isinstance(value, list), f"{label} must be a list")
    fail_fast(
        all(isinstance(item, str) and item for item in value),
        f"{label} must contain only non-empty strings",
    )
    fail_fast(len(value) == len(set(value)), f"{label} contains duplicates")
    return list(value)


def _matrix_dependencies(row: dict) -> list[str]:
    consumes_from = row.get("consumes_from")
    fail_fast(isinstance(consumes_from, dict), f"{row.get('module_id')} consumes_from must be a mapping")
    return _string_list(
        consumes_from.get("modules", []),
        f"{row.get('module_id')} consumes_from.modules",
    )


def _matrix_inputs(row: dict) -> list[str]:
    consumes_from = row.get("consumes_from")
    fail_fast(isinstance(consumes_from, dict), f"{row.get('module_id')} consumes_from must be a mapping")
    return _string_list(
        consumes_from.get("artifacts", []),
        f"{row.get('module_id')} consumes_from.artifacts",
    )


def _matrix_outputs(row: dict) -> list[str]:
    emits_to = row.get("emits_to")
    fail_fast(isinstance(emits_to, dict), f"{row.get('module_id')} emits_to must be a mapping")
    return _string_list(
        emits_to.get("artifacts", []),
        f"{row.get('module_id')} emits_to.artifacts",
    )


def _validate_matrix(rows: list[dict]) -> None:
    fail_fast(bool(rows), "module IO matrix must contain modules")
    fail_fast(all(isinstance(row, dict) for row in rows), "module IO matrix rows must be mappings")

    module_ids = [row.get("module_id") for row in rows]
    fail_fast(
        all(isinstance(module_id, str) and module_id for module_id in module_ids),
        "each matrix row must declare a non-empty module_id",
    )
    fail_fast(len(module_ids) == len(set(module_ids)), "module IO matrix contains duplicate module_id")
    known_modules = set(module_ids)
    producers: dict[str, str] = {}

    for row in rows:
        module_id = row["module_id"]
        fail_fast(
            isinstance(row.get("module_name"), str) and bool(row["module_name"]),
            f"{module_id} must declare module_name",
        )
        fail_fast(
            isinstance(row.get("subphase"), str) and bool(row["subphase"]),
            f"{module_id} must declare subphase",
        )
        fail_fast(
            isinstance(row.get("module_contract"), str) and bool(row["module_contract"]),
            f"{module_id} must declare module_contract",
        )
        unknown = sorted(set(_matrix_dependencies(row)) - known_modules)
        fail_fast(not unknown, f"{module_id} has unknown module dependencies: {unknown}")
        fail_fast(module_id not in _matrix_dependencies(row), f"{module_id} cannot depend on itself")
        _matrix_inputs(row)
        for artifact in _matrix_outputs(row):
            fail_fast(
                artifact not in producers,
                f"artifact {artifact} has multiple producers: {producers.get(artifact)} and {module_id}",
            )
            producers[artifact] = module_id


def _topological_order(rows: list[dict]) -> list[dict]:
    _validate_matrix(rows)
    row_by_id = {row.get("module_id"): row for row in rows}
    index_by_id = {row.get("module_id"): idx for idx, row in enumerate(rows)}
    deps = {
        module_id: _matrix_dependencies(row)
        for module_id, row in row_by_id.items()
    }
    pending = sorted([module_id for module_id, dep_list in deps.items() if not dep_list], key=index_by_id.get)
    ordered: list[dict] = []
    while pending:
        module_id = pending.pop(0)
        ordered.append(row_by_id[module_id])
        for other_id, dep_list in deps.items():
            if module_id in dep_list:
                dep_list.remove(module_id)
                if not dep_list and row_by_id[other_id] not in ordered and other_id not in pending:
                    pending.append(other_id)
                    pending.sort(key=index_by_id.get)
    fail_fast(len(ordered) == len(rows), "module dependency cycle or unresolved contract reference")
    return ordered


def _assert_dependencies_executed(row: dict, executed_modules: set[str]) -> None:
    missing = sorted(set(_matrix_dependencies(row)) - executed_modules)
    fail_fast(not missing, f"{row.get('module_id')} dependencies were not executed: {missing}")


def _validate_contract_against_matrix(module_contract: dict, row: dict) -> None:
    module_id = row["module_id"]
    expected_identity = {
        "module_id": module_id,
        "module_name": row["module_name"],
        "subphase": row["subphase"],
    }
    for field, expected in expected_identity.items():
        fail_fast(
            module_contract.get(field) == expected,
            f"{module_id} contract {field} mismatch: expected {expected!r}, got {module_contract.get(field)!r}",
        )

    contract_inputs = _string_list(module_contract.get("inputs"), f"{module_id} contract inputs")
    contract_outputs = _string_list(module_contract.get("outputs"), f"{module_id} contract outputs")
    fail_fast(
        contract_inputs == _matrix_inputs(row),
        f"{module_id} contract inputs do not match the IO matrix",
    )
    fail_fast(
        contract_outputs == _matrix_outputs(row),
        f"{module_id} contract outputs do not match the IO matrix",
    )


def _validate_module_result(result: Any, row: dict, module_contract: dict) -> dict[str, Any]:
    module_id = row["module_id"]
    fail_fast(isinstance(result, dict), f"{module_id} result must be a mapping")
    expected_identity = {
        "module_id": module_id,
        "module_name": row["module_name"],
        "subphase": row["subphase"],
        "phase": module_contract.get("phase"),
        "contract": Path(row["module_contract"]).name,
    }
    for field, expected in expected_identity.items():
        fail_fast(
            result.get(field) == expected,
            f"{module_id} result {field} mismatch: expected {expected!r}, got {result.get(field)!r}",
        )

    expected_inputs = _matrix_inputs(row)
    result_inputs = _string_list(result.get("required_inputs"), f"{module_id} result required_inputs")
    fail_fast(
        result_inputs == expected_inputs,
        f"{module_id} result required_inputs do not match the IO matrix",
    )
    outputs = result.get("outputs")
    fail_fast(isinstance(outputs, dict), f"{module_id} result outputs must be a mapping")
    expected_outputs = _matrix_outputs(row)
    actual_outputs = list(outputs)
    fail_fast(
        len(actual_outputs) == len(expected_outputs) and set(actual_outputs) == set(expected_outputs),
        f"{module_id} outputs mismatch: expected exactly {expected_outputs}, got {actual_outputs}",
    )
    return outputs


_TYPE_CHECKS = {
    "object": lambda value: isinstance(value, dict),
    "mapping": lambda value: isinstance(value, dict),
    "dict": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "list": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "bool": lambda value: isinstance(value, bool),
    "null": lambda value: value is None,
}


def _matches_declared_type(value: Any, declared: Any) -> bool:
    names = declared if isinstance(declared, list) else [declared]
    fail_fast(
        bool(names) and all(isinstance(name, str) and name in _TYPE_CHECKS for name in names),
        f"unsupported schema type declaration: {declared!r}",
    )
    return any(_TYPE_CHECKS[name](value) for name in names)


def _validate_structure(value: Any, schema: dict, path: str) -> None:
    canonical_validate_schema_value(value, schema, path)
    return
    # Retained below only as an unreachable compatibility reference for old
    # line-oriented evidence; runtime validation returns through the canonical
    # implementation above.
    for keyword in ("allOf", "anyOf", "oneOf"):
        if keyword in schema:
            branches = schema[keyword]
            fail_fast(isinstance(branches, list) and branches, f"{path} schema {keyword} must be a non-empty list")
            outcomes = []
            for branch in branches:
                try:
                    fail_fast(isinstance(branch, dict), f"{path} schema {keyword} branch must be a mapping")
                    _validate_structure(value, branch, path)
                    outcomes.append(True)
                except ValueError:
                    outcomes.append(False)
            matches = sum(outcomes)
            valid = matches == len(outcomes) if keyword == "allOf" else matches >= 1 if keyword == "anyOf" else matches == 1
            fail_fast(valid, f"{path} does not satisfy {keyword}")
    if "not" in schema:
        rejected = False
        try:
            fail_fast(isinstance(schema["not"], dict), f"{path} schema not must be a mapping")
            _validate_structure(value, schema["not"], path)
        except ValueError:
            rejected = True
        fail_fast(rejected, f"{path} satisfies forbidden not schema")
    declared_type = schema.get("type")
    if declared_type is not None:
        fail_fast(
            _matches_declared_type(value, declared_type),
            f"{path} must have schema type {declared_type!r}",
        )

    if "enum" in schema:
        enum_values = schema["enum"]
        fail_fast(isinstance(enum_values, list), f"{path} schema enum must be a list")
        fail_fast(value in enum_values, f"{path} is not one of the allowed enum values")

    if "const" in schema:
        fail_fast(value == schema["const"], f"{path} must equal schema const")

    if "pattern" in schema:
        fail_fast(isinstance(value, str), f"{path} must be a string to apply pattern")
        fail_fast(re.search(str(schema["pattern"]), value) is not None, f"{path} does not match schema pattern")

    if "minLength" in schema:
        fail_fast(isinstance(value, str), f"{path} must be a string to apply minLength")
        fail_fast(len(value) >= int(schema["minLength"]), f"{path} is shorter than minLength")
    if "maxLength" in schema:
        fail_fast(isinstance(value, str), f"{path} must be a string to apply maxLength")
        fail_fast(len(value) <= int(schema["maxLength"]), f"{path} is longer than maxLength")

    for keyword, comparator, message in (("minimum", lambda actual, limit: actual >= limit, "below minimum"), ("maximum", lambda actual, limit: actual <= limit, "above maximum")):
        if keyword in schema:
            fail_fast(isinstance(value, (int, float)) and not isinstance(value, bool), f"{path} must be numeric to apply {keyword}")
            fail_fast(comparator(value, schema[keyword]), f"{path} is {message}")

    if "minItems" in schema:
        fail_fast(isinstance(value, list), f"{path} must be a list to apply minItems")
        fail_fast(len(value) >= int(schema["minItems"]), f"{path} has fewer items than minItems")
    if "maxItems" in schema:
        fail_fast(isinstance(value, list), f"{path} must be a list to apply maxItems")
        fail_fast(len(value) <= int(schema["maxItems"]), f"{path} has more items than maxItems")
    if schema.get("uniqueItems"):
        fail_fast(isinstance(value, list), f"{path} must be a list to apply uniqueItems")
        encoded = [json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False) for item in value]
        fail_fast(len(encoded) == len(set(encoded)), f"{path} contains duplicate items")

    properties = schema.get("properties")
    structure = schema.get("structure")
    if properties is None and isinstance(structure, dict):
        properties = structure
    if properties is not None:
        fail_fast(isinstance(value, dict), f"{path} must be a mapping to validate properties")
        fail_fast(isinstance(properties, dict), f"{path} schema properties must be a mapping")
        required = _string_list(schema.get("required", []), f"{path} schema required")
        missing = [field for field in required if field not in value]
        fail_fast(not missing, f"{path} missing required structured fields: {missing}")
        if "minProperties" in schema:
            fail_fast(len(value) >= int(schema["minProperties"]), f"{path} has fewer properties than minProperties")
        if "maxProperties" in schema:
            fail_fast(len(value) <= int(schema["maxProperties"]), f"{path} has more properties than maxProperties")
        for field, field_schema in properties.items():
            fail_fast(isinstance(field, str) and field, f"{path} schema property names must be strings")
            fail_fast(isinstance(field_schema, dict), f"{path}.{field} schema must be a mapping")
            if field in value:
                _validate_structure(value[field], field_schema, f"{path}.{field}")
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            fail_fast(not extra, f"{path} has undeclared structured fields: {extra}")

    items = schema.get("items")
    if items is not None:
        fail_fast(isinstance(value, list), f"{path} must be a list to validate items")
        fail_fast(isinstance(items, dict), f"{path} schema items must be a mapping")
        for index, item in enumerate(value):
            _validate_structure(item, items, f"{path}[{index}]")


def _forbidden_paths(value: Any, forbidden_fields: set[str], path: str = "") -> list[str]:
    found: list[str] = []
    normalized_forbidden = {normalize_field_name(field) for field in forbidden_fields}
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}" if path else str(key)
            if normalize_field_name(key) in normalized_forbidden:
                found.append(item_path)
            found.extend(_forbidden_paths(item, forbidden_fields, item_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_forbidden_paths(item, forbidden_fields, f"{path}[{index}]"))
    return found


def _validate_artifact(artifact_name: str, artifact: Any) -> None:
    schema_path = SCHEMA_ROOT / f"{artifact_name}.schema.yaml"
    fail_fast(schema_path.is_file(), f"missing schema for emitted artifact: {artifact_name}")
    schema = _load_yaml(schema_path)
    fail_fast(
        schema.get("artifact_name") == artifact_name,
        f"schema artifact_name mismatch for {artifact_name}",
    )
    fail_fast(isinstance(artifact, dict), f"{artifact_name} must be a mapping")

    required_fields = _string_list(
        schema.get("required_fields", []),
        f"{artifact_name} schema required_fields",
    )
    missing = [
        field
        for field in required_fields
        if field not in artifact or artifact[field] is None or artifact[field] == ""
    ]
    fail_fast(not missing, f"{artifact_name} missing required fields: {missing}")

    forbidden_fields = set(
        _string_list(schema.get("forbidden_fields", []), f"{artifact_name} schema forbidden_fields")
    )
    leaked = _forbidden_paths(artifact, forbidden_fields)
    fail_fast(not leaked, f"{artifact_name} contains forbidden fields: {leaked}")

    field_types = schema.get("field_types", {})
    fail_fast(isinstance(field_types, dict), f"{artifact_name} schema field_types must be a mapping")
    for field, declared_type in field_types.items():
        if field in artifact:
            fail_fast(
                _matches_declared_type(artifact[field], declared_type),
                f"{artifact_name}.{field} must have schema type {declared_type!r}",
            )
    _validate_structure(artifact, schema, artifact_name)


def _merge_outputs(context: dict, outputs: dict[str, Any], module_id: str) -> None:
    collisions = sorted(set(outputs).intersection(context))
    fail_fast(
        not collisions,
        f"{module_id} attempted to overwrite existing artifacts: {collisions}",
    )
    context.update(outputs)


def run_phase(inputs: dict, config: dict) -> dict:
    fail_fast(isinstance(inputs, dict), "inputs must be an explicit dict")
    fail_fast(isinstance(config, dict), "config must be an explicit dict")

    input_contract = _load_yaml(CONTRACT_ROOT / "INPUT_CONTRACTS.yaml")
    output_contract = _load_yaml(CONTRACT_ROOT / "OUTPUT_CONTRACTS.yaml")
    module_io_matrix = _load_yaml(CONTRACT_ROOT / "MODULE_IO_MATRIX.yaml")

    required_inputs = _string_list(input_contract.get("required_inputs", []), "phase required_inputs")
    missing_inputs = [name for name in required_inputs if name not in inputs]
    fail_fast(not missing_inputs, f"missing required phase inputs: {missing_inputs}")
    forbidden_inputs = set(
        _string_list(input_contract.get("forbidden_inputs", []), "phase forbidden_inputs")
    )
    leaked_inputs = sorted(forbidden_inputs.intersection(inputs))
    fail_fast(not leaked_inputs, f"forbidden phase inputs: {leaked_inputs}")

    context = dict(inputs)
    module_results = []
    raw_rows = module_io_matrix.get("module_io_matrix", [])
    fail_fast(isinstance(raw_rows, list), "module_io_matrix must be a list")
    ordered_rows = _topological_order(list(raw_rows))
    executed_modules: set[str] = set()

    for row in ordered_rows:
        _assert_dependencies_executed(row, executed_modules)
        contract_filename = row.get("module_contract")
        fail_fast(bool(contract_filename), f"missing module contract for {row.get('module_id')}")
        module = import_module(_module_path(contract_filename))
        module_contract = _load_yaml(MODULE_ROOT / Path(contract_filename).name)
        _validate_contract_against_matrix(module_contract, row)
        module_required_inputs = _matrix_inputs(row)
        module_inputs = {name: context[name] for name in module_required_inputs if name in context}
        missing_module_inputs = [name for name in module_required_inputs if name not in module_inputs]
        fail_fast(not missing_module_inputs, f"{contract_filename} missing inputs: {missing_module_inputs}")
        result = module.run_module(module_inputs, config)
        outputs = _validate_module_result(result, row, module_contract)
        for artifact_name, artifact in outputs.items():
            _validate_artifact(artifact_name, artifact)
        _merge_outputs(context, outputs, row["module_id"])
        module_results.append(result)
        executed_modules.add(row["module_id"])

    declared_outputs = _string_list(output_contract.get("outputs", []), "phase declared_outputs")
    phase_outputs = {name: context[name] for name in declared_outputs if name in context}
    missing_phase_outputs = [name for name in declared_outputs if name not in phase_outputs]
    fail_fast(not missing_phase_outputs, f"missing declared phase outputs: {missing_phase_outputs}")
    forbidden_output_fields = set(
        _string_list(
            output_contract.get("forbidden_output_fields", []),
            "phase forbidden_output_fields",
        )
    )
    leaked_output_paths = _forbidden_paths(phase_outputs, forbidden_output_fields)
    fail_fast(not leaked_output_paths, f"forbidden phase output fields: {leaked_output_paths}")

    return {
        "phase": input_contract.get("phase", PHASE_NAME),
        "validation_mode": "contract_pipeline",
        "required_inputs": required_inputs,
        "received_inputs": sorted(inputs),
        "config_keys": sorted(config),
        "declared_outputs": declared_outputs,
        "module_results": module_results,
        "phase_outputs": phase_outputs,
        "context": context,
    }
