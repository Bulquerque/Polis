from __future__ import annotations

from typing import Any
import json
import re

from ._module_executor import ContractValidationError


def _type_matches(value: Any, declared: Any) -> bool:
    checks = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "null": lambda v: v is None,
    }
    names = declared if isinstance(declared, list) else [declared]
    if not names or any(name not in checks for name in names):
        raise ContractValidationError(f"unsupported schema type declaration: {declared!r}")
    return any(checks[name](value) for name in names)


def validate_schema_value(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    if not isinstance(schema, dict):
        raise ContractValidationError(f"{path} schema must be a mapping")
    for keyword in ("allOf", "anyOf", "oneOf"):
        if keyword in schema:
            branches = schema[keyword]
            if not isinstance(branches, list) or not branches:
                raise ContractValidationError(f"{path} schema {keyword} must be a non-empty list")
            matches = 0
            for branch in branches:
                try:
                    validate_schema_value(value, branch, path)
                except ContractValidationError:
                    continue
                matches += 1
            valid = matches == len(branches) if keyword == "allOf" else matches >= 1 if keyword == "anyOf" else matches == 1
            if not valid:
                raise ContractValidationError(f"{path} does not satisfy {keyword}")
    if "not" in schema:
        try:
            validate_schema_value(value, schema["not"], path)
        except ContractValidationError:
            pass
        else:
            raise ContractValidationError(f"{path} satisfies forbidden not schema")
    if "type" in schema and not _type_matches(value, schema["type"]):
        raise ContractValidationError(f"{path} must have schema type {schema['type']!r}")
    if isinstance(value, dict):
        required = schema.get("required", schema.get("required_fields", []))
        if not isinstance(required, list):
            raise ContractValidationError(f"{path} required fields must be a list")
        missing = [field for field in required if field not in value]
        if missing:
            raise ContractValidationError(f"{path} missing required fields: {missing}")
    if "enum" in schema and (not isinstance(schema["enum"], list) or value not in schema["enum"]):
        raise ContractValidationError(f"{path} is not one of the allowed enum values")
    if "const" in schema and value != schema["const"]:
        raise ContractValidationError(f"{path} must equal schema const")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise ContractValidationError(f"{path} is shorter than minLength")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ContractValidationError(f"{path} is longer than maxLength")
        if "pattern" in schema and re.search(str(schema["pattern"]), value) is None:
            raise ContractValidationError(f"{path} does not match schema pattern")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ContractValidationError(f"{path} is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ContractValidationError(f"{path} is above maximum")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            raise ContractValidationError(f"{path} has fewer items than minItems")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ContractValidationError(f"{path} has more items than maxItems")
        if schema.get("uniqueItems"):
            encoded = [json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False) for item in value]
            if len(encoded) != len(set(encoded)):
                raise ContractValidationError(f"{path} contains duplicate items")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(value):
                validate_schema_value(item, schema["items"], f"{path}[{index}]")
    properties = schema.get("properties")
    if properties is None and isinstance(schema.get("structure"), dict):
        properties = schema["structure"]
    if isinstance(value, dict) and properties is not None:
        if not isinstance(properties, dict):
            raise ContractValidationError(f"{path} schema properties must be a mapping")
        required = schema.get("required", schema.get("required_fields", []))
        missing = [field for field in required if field not in value]
        if missing:
            raise ContractValidationError(f"{path} missing required fields: {missing}")
        if "minProperties" in schema and len(value) < int(schema["minProperties"]):
            raise ContractValidationError(f"{path} has fewer properties than minProperties")
        if "maxProperties" in schema and len(value) > int(schema["maxProperties"]):
            raise ContractValidationError(f"{path} has more properties than maxProperties")
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                raise ContractValidationError(
                    f"undeclared structured fields (output schema extra fields) at {path}: {extras}"
                )
        for key, child_schema in properties.items():
            if key in value:
                validate_schema_value(value[key], child_schema, f"{path}.{key}")
