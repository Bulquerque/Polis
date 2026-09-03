from __future__ import annotations

from typing import Any
import re

from ._module_executor import ContractValidationError, SCHEMA_ROOT
from ._s5_core import find_forbidden_fields, load_yaml_mapping
from ._canonical_schema_validator import validate_schema_value as canonical_validate_schema_value


def _validate_type(value: Any, schema: dict[str, Any], path: str) -> None:
    type_name = schema.get("type")
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
    }
    if type_name in checks and not checks[type_name](value):
        raise ContractValidationError(f"output schema type mismatch at {path}: {type_name}")


def _validate_string(value: Any, schema: dict[str, Any], path: str) -> None:
    if not isinstance(value, str):
        return
    if len(value) < int(schema.get("minLength", 0)):
        raise ContractValidationError(f"output schema minLength mismatch at {path}")
    pattern = schema.get("pattern")
    if pattern and re.fullmatch(str(pattern), value) is None:
        raise ContractValidationError(f"output schema pattern mismatch at {path}")


def _validate_constraints(value: Any, schema: dict[str, Any], path: str) -> None:
    if "const" in schema and value != schema["const"]:
        raise ContractValidationError(f"output schema const mismatch at {path}")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractValidationError(f"output schema enum mismatch at {path}")
    _validate_string(value, schema, path)
    minimum = schema.get("minimum")
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    if numeric and minimum is not None and value < minimum:
        raise ContractValidationError(f"output schema minimum mismatch at {path}")


def _validate_array(value: Any, schema: dict[str, Any], path: str) -> None:
    if not isinstance(value, list):
        return
    if len(value) < int(schema.get("minItems", 0)):
        raise ContractValidationError(f"output schema minItems mismatch at {path}")
    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        for index, item in enumerate(value):
            validate_schema_value(item, item_schema, f"{path}[{index}]")


def _validate_object(value: Any, schema: dict[str, Any], path: str) -> None:
    if not isinstance(value, dict):
        return
    required = schema.get("required_fields", schema.get("required", []))
    missing = [field for field in required if field not in value]
    if missing:
        raise ContractValidationError(f"output schema missing fields at {path}: {missing}")
    properties = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        extras = sorted(set(value) - set(properties))
        if extras:
            raise ContractValidationError(f"output schema extra fields at {path}: {extras}")
    for key, child in value.items():
        child_schema = properties.get(key)
        if isinstance(child_schema, dict):
            validate_schema_value(child, child_schema, f"{path}.{key}")


def validate_schema_value(value: Any, schema: dict[str, Any], path: str) -> None:
    _validate_type(value, schema, path)
    _validate_constraints(value, schema, path)
    _validate_array(value, schema, path)
    _validate_object(value, schema, path)


def validate_artifact(artifact: dict[str, Any], schema_name: str, label: str) -> None:
    schema = load_yaml_mapping(SCHEMA_ROOT / schema_name, f"{label} schema")
    validate_schema_value(artifact, schema, label)
    leaked = find_forbidden_fields(artifact, label)
    if leaked:
        raise ContractValidationError(f"forbidden output fields detected: {leaked}")


# The canonical validator is the only implementation used by S5 runtime calls.
validate_schema_value = canonical_validate_schema_value
