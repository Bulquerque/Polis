from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
import hashlib
import json
import re
from datetime import datetime, timezone

import yaml

from ._module_executor import ContractValidationError
from ..validators import FORBIDDEN_ECONOMIC_FIELDS, normalize_field_name


BOUNDARY_FORBIDDEN_FIELDS = set(FORBIDDEN_ECONOMIC_FIELDS)


def load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    """Load a YAML mapping and fail closed on malformed or missing content."""
    if not path.is_file():
        raise ContractValidationError(f"{label} does not exist: {path}")
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ContractValidationError(f"invalid YAML for {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractValidationError(f"{label} must be a YAML mapping: {path}")
    return value


def load_yaml_mapping_malformed(path: Path, label: str) -> dict[str, Any]:
    """Compatibility loader preserving M01's historical error wording."""
    if not path.is_file():
        raise ContractValidationError(f"{label} does not exist: {path}")
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ContractValidationError(f"malformed YAML for {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractValidationError(f"malformed {label} mapping: {path}")
    return value


def find_forbidden_fields(
    value: Any,
    path: str = "inputs",
    forbidden_fields: set[str] | None = None,
) -> list[str]:
    """Recursively detect economic payload fields at a technical boundary."""
    forbidden = BOUNDARY_FORBIDDEN_FIELDS if forbidden_fields is None else forbidden_fields
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text in forbidden:
                findings.append(child_path)
            findings.extend(find_forbidden_fields(child, child_path, forbidden))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(find_forbidden_fields(child, f"{path}[{index}]", forbidden))
    return findings


def normalized_version(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def created_at(config: dict[str, Any]) -> str:
    value = config.get("created_at") or config.get("generated_at") or config.get("evaluation_time")
    if value:
        return str(value)
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def string_list(value: Any, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ContractValidationError(f"{label} must be a list of non-empty strings")
    if not allow_empty and not value:
        raise ContractValidationError(f"{label} must not be empty")
    if len(value) != len(set(value)):
        raise ContractValidationError(f"{label} contains duplicates")
    return list(value)


def resolve_repo_path(
    value: Any,
    label: str,
    repository_root: Path,
    *,
    must_exist: bool = False,
    escape_message: str = "contains path traversal",
) -> tuple[Path, str]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ContractValidationError(f"{label} must be a repository-relative POSIX path")
    pure_path = PurePosixPath(value)
    if pure_path.is_absolute() or ".." in pure_path.parts:
        raise ContractValidationError(f"{label} {escape_message}: {value}")
    root = repository_root.resolve()
    resolved = (root / Path(*pure_path.parts)).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ContractValidationError(f"{label} is outside repository: {value}") from exc
    if must_exist and not resolved.is_file():
        raise ContractValidationError(f"{label} does not exist: {value}")
    return resolved, pure_path.as_posix()


def validate_schema_value(value: Any, schema: dict[str, Any], path: str) -> None:
    """Validate the strict schema subset used by P0 runtime artifacts."""
    type_name = schema.get("type")
    if isinstance(type_name, list):
        if not any(_matches_type(value, item) for item in type_name):
            raise ContractValidationError(f"output schema type mismatch at {path}: {type_name}")
    elif isinstance(type_name, str) and not _matches_type(value, type_name):
        raise ContractValidationError(f"output schema type mismatch at {path}: {type_name}")

    if "const" in schema and value != schema["const"]:
        raise ContractValidationError(f"output schema const mismatch at {path}")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractValidationError(f"output schema enum mismatch at {path}")

    if isinstance(value, str):
        pattern = schema.get("pattern")
        if pattern and re.fullmatch(str(pattern), value) is None:
            raise ContractValidationError(f"output schema pattern mismatch at {path}")
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise ContractValidationError(f"output schema minLength mismatch at {path}")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ContractValidationError(f"output schema maxLength mismatch at {path}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ContractValidationError(f"output schema minimum mismatch at {path}")
        if "maximum" in schema and value > schema["maximum"]:
            raise ContractValidationError(f"output schema maximum mismatch at {path}")

    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            raise ContractValidationError(f"output schema minItems mismatch at {path}")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ContractValidationError(f"output schema maxItems mismatch at {path}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                validate_schema_value(item, item_schema, f"{path}[{index}]")

    if isinstance(value, dict):
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
            descriptor = properties.get(key) if isinstance(properties, dict) else None
            if isinstance(descriptor, dict):
                validate_schema_value(child, descriptor, f"{path}.{key}")


def _matches_type(value: Any, type_name: str) -> bool:
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    check = checks.get(type_name)
    return True if check is None else bool(check(value))


def materialized_artifact(value: Any, label: str, required: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) == {"source"}:
        raise ContractValidationError(f"{label} must be a materialized artifact, not a placeholder")
    missing = sorted(required.difference(value))
    if missing:
        raise ContractValidationError(f"{label} is malformed; missing fields: {missing}")
    lineage = value.get("lineage_id")
    if not isinstance(lineage, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", lineage) is None:
        raise ContractValidationError(f"{label} lineage_id is malformed")
    return value


from ._canonical_schema_validator import validate_schema_value as _canonical_validate_schema_value  # noqa: E402
validate_schema_value = _canonical_validate_schema_value
