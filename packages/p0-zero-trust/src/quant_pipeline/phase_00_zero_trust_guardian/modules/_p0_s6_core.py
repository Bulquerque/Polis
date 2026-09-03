from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import re
from datetime import datetime, timezone

import yaml

from ._module_executor import ContractValidationError, PIPELINE_VERSION, SCHEMA_ROOT
from ..validators import FORBIDDEN_ECONOMIC_FIELDS, normalize_field_name

FORBIDDEN_FIELDS = set(FORBIDDEN_ECONOMIC_FIELDS)
DEFAULT_PHASE_IDS = tuple(f"P{i}" for i in range(10))
SOURCE_STATUSES = {"PASS", "FAIL"}
S6_STATUSES = {"PASS", "FAIL"}


def require_inputs(inputs: Any, names: set[str]) -> dict[str, Any]:
    if not isinstance(inputs, dict):
        raise ContractValidationError("inputs must be a dict")
    missing = sorted(names - set(inputs))
    if missing:
        raise ContractValidationError(f"missing required inputs: {missing}")
    leaked = find_forbidden_fields(inputs)
    if leaked:
        raise ContractValidationError(f"forbidden input fields detected: {leaked}")
    return inputs


def require_config(config: Any) -> dict[str, Any]:
    if config is None:
        return {}
    if not isinstance(config, dict):
        raise ContractValidationError("config must be a dict")
    return config


def materialized(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value or set(value) == {"source"}:
        raise ContractValidationError(f"{label} must be a materialized mapping")
    return value


def source_control(value: Any, label: str) -> dict[str, Any]:
    item = materialized(value, label)
    _validate_identity(item, label)
    if item.get("status") not in SOURCE_STATUSES:
        raise ContractValidationError(f"{label} has invalid status")
    if not isinstance(item.get("release_blocking"), bool):
        raise ContractValidationError(f"{label}.release_blocking must be boolean")
    if (item["status"] == "FAIL") != item["release_blocking"]:
        raise ContractValidationError(f"{label} has inconsistent status controls")
    return item


def s6_control(value: Any, label: str) -> dict[str, Any]:
    item = materialized(value, label)
    _validate_identity(item, label)
    if item.get("status") not in S6_STATUSES:
        raise ContractValidationError(f"{label} has invalid S6 status")
    if not isinstance(item.get("release_blocking"), bool):
        raise ContractValidationError(f"{label}.release_blocking must be boolean")
    return item


def _validate_identity(item: dict[str, Any], label: str) -> None:
    artifact_id = item.get("artifact_id")
    lineage_id = item.get("lineage_id")
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        raise ContractValidationError(f"{label}.artifact_id is invalid")
    if not isinstance(lineage_id, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", lineage_id) is None:
        raise ContractValidationError(f"{label}.lineage_id is invalid")


def find_forbidden_fields(value: Any, path: str = "inputs") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if normalize_field_name(key) in {normalize_field_name(field) for field in FORBIDDEN_FIELDS}:
                findings.append(child_path)
            findings.extend(find_forbidden_fields(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(find_forbidden_fields(child, f"{path}[{index}]"))
    return findings


def digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def created_at(config: dict[str, Any]) -> str:
    supplied = config.get("created_at") or config.get("generated_at") or config.get("evaluation_time")
    if supplied:
        if not isinstance(supplied, str):
            raise ContractValidationError("created_at must be a string")
        return supplied
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def envelope(name: str, payload: Any, config: dict[str, Any]) -> dict[str, Any]:
    value = digest(payload)
    return {
        "artifact_id": f"{name.replace('_', '-')}-{value[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{value}",
    }


def load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ContractValidationError(f"invalid YAML for {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractValidationError(f"invalid {label} mapping")
    return value


def validate(artifact: dict[str, Any], schema_name: str, label: str) -> None:
    schema = load_yaml_mapping(SCHEMA_ROOT / schema_name, f"{label} schema")
    validate_schema_value(artifact, schema, label)
    leaked = find_forbidden_fields(artifact, label)
    if leaked:
        raise ContractValidationError(f"forbidden output fields detected: {leaked}")


def validate_schema_value(value: Any, schema: dict[str, Any], path: str) -> None:
    _validate_scalar(value, schema, path)
    if isinstance(value, list):
        _validate_list(value, schema, path)
    if isinstance(value, dict):
        _validate_mapping(value, schema, path)


def _validate_scalar(value: Any, schema: dict[str, Any], path: str) -> None:
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
    }
    type_name = schema.get("type")
    if type_name in checks and not checks[type_name](value):
        raise ContractValidationError(f"output schema type mismatch at {path}: {type_name}")
    if "const" in schema and value != schema["const"]:
        raise ContractValidationError(f"output schema const mismatch at {path}")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractValidationError(f"output schema enum mismatch at {path}")
    if isinstance(value, str) and schema.get("pattern"):
        if re.fullmatch(str(schema["pattern"]), value) is None:
            raise ContractValidationError(f"output schema pattern mismatch at {path}")


def _validate_list(value: list[Any], schema: dict[str, Any], path: str) -> None:
    if len(value) < int(schema.get("minItems", 0)):
        raise ContractValidationError(f"output schema minItems mismatch at {path}")
    if "maxItems" in schema and len(value) > int(schema["maxItems"]):
        raise ContractValidationError(f"output schema maxItems mismatch at {path}")
    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        for index, item in enumerate(value):
            validate_schema_value(item, item_schema, f"{path}[{index}]")


def _validate_mapping(value: dict[str, Any], schema: dict[str, Any], path: str) -> None:
    required = schema.get("required_fields", schema.get("required", []))
    missing = [field for field in required if field not in value]
    if missing:
        raise ContractValidationError(f"output schema missing fields at {path}: {missing}")
    properties = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        extras = sorted(set(value).difference(properties))
        if extras:
            raise ContractValidationError(f"output schema extra fields at {path}: {extras}")
    for key, child in value.items():
        child_schema = properties.get(key)
        if isinstance(child_schema, dict):
            validate_schema_value(child, child_schema, f"{path}.{key}")


def result(module_id: str, module_name: str, required: list[str], outputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "module_id": module_id,
        "module_name": module_name,
        "phase": "P0",
        "subphase": "P0.S6",
        "contract": f"{module_id.replace('.', '_')}_{module_name}.yaml",
        "required_inputs": required,
        "outputs": outputs,
    }


def source_summary(item: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "source": source,
        "artifact_id": item["artifact_id"],
        "lineage_id": item["lineage_id"],
        "status": item["status"],
        "release_blocking": item["release_blocking"],
    }


from ._canonical_schema_validator import validate_schema_value as _canonical_validate_schema_value  # noqa: E402
validate_schema_value = _canonical_validate_schema_value
