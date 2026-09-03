from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import re
from datetime import datetime, timezone

import yaml

from ._module_executor import ContractValidationError, PIPELINE_VERSION, SCHEMA_ROOT, strict_json_bytes
from ..validators import FORBIDDEN_ECONOMIC_FIELDS, normalize_field_name


FORBIDDEN_FIELDS = set(FORBIDDEN_ECONOMIC_FIELDS)
PHASES = tuple(f"P{i}" for i in range(10))
PHASE_SET = set(PHASES)


def created_at(config: dict[str, Any]) -> str:
    value = config.get("created_at") or config.get("generated_at") or config.get("evaluation_time")
    if value:
        return str(value)
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def forbidden(value: Any, path: str = "inputs") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if normalize_field_name(key) in {normalize_field_name(field) for field in FORBIDDEN_FIELDS}:
                found.append(child_path)
            found.extend(forbidden(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(forbidden(child, f"{path}[{index}]"))
    return found


def require_call(inputs: Any, config: Any, names: list[str]) -> dict[str, Any]:
    if not isinstance(inputs, dict):
        raise ContractValidationError("inputs must be a dict")
    if config is not None and not isinstance(config, dict):
        raise ContractValidationError("config must be a dict")
    missing = [name for name in names if name not in inputs]
    if missing:
        raise ContractValidationError(f"missing required inputs: {missing}")
    leaked = forbidden(inputs)
    if leaked:
        raise ContractValidationError(f"forbidden input fields detected: {leaked}")
    return {} if config is None else config


def artifact(value: Any, name: str) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("outputs"), dict):
        value = value["outputs"].get(name)
    if isinstance(value, dict) and isinstance(value.get(name), dict) and len(value) == 1:
        value = value[name]
    if not isinstance(value, dict):
        raise ContractValidationError(f"{name} must be a material artifact mapping")
    return value


def digest(value: Any) -> str:
    encoded = strict_json_bytes(value).decode("utf-8")
    return hashlib.sha256(encoded.encode()).hexdigest()


def load_yaml(path: Path, label: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ContractValidationError(f"invalid {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractValidationError(f"{label} must be a mapping: {path}")
    return value


def load_schema(path: Path) -> dict[str, Any]:
    return load_yaml(path, "schema")


def repository_root(start: Path, config: dict[str, Any]) -> Path:
    explicit = config.get("repository_root")
    if explicit:
        path = Path(str(explicit)).expanduser().resolve()
        if not path.exists():
            raise ContractValidationError(f"repository_root does not exist: {path}")
        return path
    for parent in [start.resolve(), *start.resolve().parents]:
        if (parent / "global_contracts_parallel_agents").exists() and (parent / "phase_00_zero_trust").exists():
            return parent
    raise ContractValidationError("unable to resolve repository root from canonical markers")


def _validate_combinators(value: Any, schema: dict[str, Any], path: str) -> None:
    if isinstance(schema.get("allOf"), list):
        for branch in schema["allOf"]:
            validate(value, branch, path)
    if isinstance(schema.get("anyOf"), list):
        matches = 0
        for branch in schema["anyOf"]:
            try:
                validate(value, branch, path)
                matches += 1
            except ContractValidationError:
                pass
        if matches == 0:
            raise ContractValidationError(f"schema anyOf mismatch at {path}")
    if isinstance(schema.get("oneOf"), list):
        matches = 0
        for branch in schema["oneOf"]:
            try:
                validate(value, branch, path)
                matches += 1
            except ContractValidationError:
                pass
        if matches != 1:
            raise ContractValidationError(f"schema oneOf mismatch at {path}")
    if isinstance(schema.get("not"), dict):
        try:
            validate(value, schema["not"], path)
        except ContractValidationError:
            return
        raise ContractValidationError(f"schema not mismatch at {path}")


def validate(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    _validate_combinators(value, schema, path)
    kind = schema.get("type")
    checks = {
        "object": lambda x: isinstance(x, dict),
        "array": lambda x: isinstance(x, list),
        "string": lambda x: isinstance(x, str),
        "integer": lambda x: isinstance(x, int) and not isinstance(x, bool),
        "number": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool),
        "boolean": lambda x: isinstance(x, bool),
        "null": lambda x: x is None,
    }
    if kind in checks and not checks[kind](value):
        raise ContractValidationError(f"schema type mismatch at {path}: {kind}")
    if "const" in schema and value != schema["const"]:
        raise ContractValidationError(f"schema const mismatch at {path}")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractValidationError(f"schema enum mismatch at {path}")
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            raise ContractValidationError(f"schema minLength mismatch at {path}")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ContractValidationError(f"schema maxLength mismatch at {path}")
        if schema.get("pattern") and re.fullmatch(str(schema["pattern"]), value) is None:
            raise ContractValidationError(f"schema pattern mismatch at {path}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ContractValidationError(f"schema minimum mismatch at {path}")
        if "maximum" in schema and value > schema["maximum"]:
            raise ContractValidationError(f"schema maximum mismatch at {path}")
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            raise ContractValidationError(f"schema minItems mismatch at {path}")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ContractValidationError(f"schema maxItems mismatch at {path}")
        if schema.get("uniqueItems") and len({digest(item) for item in value}) != len(value):
            raise ContractValidationError(f"schema uniqueItems mismatch at {path}")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(value):
                validate(item, schema["items"], f"{path}[{index}]")
    if isinstance(value, dict):
        required = schema.get("required_fields", schema.get("required", []))
        if not isinstance(required, list):
            raise ContractValidationError(f"schema required fields malformed at {path}")
        missing = [key for key in required if key not in value]
        if missing:
            raise ContractValidationError(f"schema required fields missing at {path}: {missing}")
        if len(value) < int(schema.get("minProperties", 0)):
            raise ContractValidationError(f"schema minProperties mismatch at {path}")
        if "maxProperties" in schema and len(value) > int(schema["maxProperties"]):
            raise ContractValidationError(f"schema maxProperties mismatch at {path}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value).difference(props))
            if extras:
                raise ContractValidationError(f"schema extra fields at {path}: {extras}")
        if isinstance(props, dict):
            for key, child in value.items():
                if isinstance(props.get(key), dict):
                    validate(child, props[key], f"{path}.{key}")


def validate_output(value: dict[str, Any], schema_name: str) -> None:
    validate(value, load_schema(SCHEMA_ROOT / schema_name), schema_name)
    leaked = forbidden(value, schema_name)
    if leaked:
        raise ContractValidationError(f"forbidden output fields detected: {leaked}")


def envelope(module_id: str, module_name: str, inputs: list[str], outputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "module_id": module_id,
        "module_name": module_name,
        "phase": "P0",
        "subphase": "P0.S4",
        "contract": f"{module_id.replace('.', '_')}_{module_name}.yaml",
        "required_inputs": inputs,
        "outputs": outputs,
    }


from ._canonical_schema_validator import validate_schema_value as _canonical_validate_schema_value  # noqa: E402
validate = _canonical_validate_schema_value
