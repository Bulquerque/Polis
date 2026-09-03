from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Iterable
import hashlib
import json
import re
from datetime import datetime, timezone

import yaml

from ._module_executor import ContractValidationError, PIPELINE_VERSION, SCHEMA_ROOT, strict_json_bytes
from ..validators import FORBIDDEN_ECONOMIC_FIELDS, normalize_field_name
from ._canonical_schema_validator import validate_schema_value as canonical_validate_schema_value

FORBIDDEN_FIELDS = set(FORBIDDEN_ECONOMIC_FIELDS)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LINEAGE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CANONICAL_HASH_ALGORITHM = "sha256"
HASH_CHUNK_SIZE = 1024 * 1024


def workspace_root() -> Path:
    """Resolve the repository workspace without relying on a fixed parent depth."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "phase_00_zero_trust").is_dir():
            return parent
    raise ContractValidationError("unable to resolve repository workspace root")


def created_at(config: dict[str, Any]) -> str:
    value = config.get("created_at") or config.get("generated_at") or config.get("evaluation_time")
    if value:
        return str(value)
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalized_version(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def require_runtime_version(config: dict[str, Any]) -> None:
    runtime = str(config.get("pipeline_version") or PIPELINE_VERSION)
    if normalized_version(runtime) != normalized_version(PIPELINE_VERSION):
        raise ContractValidationError("pipeline version is incompatible")


def load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ContractValidationError(f"{label} does not exist: {path}")
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ContractValidationError(f"invalid YAML for {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractValidationError(f"invalid {label} mapping: {path}")
    return value


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


def validate_no_forbidden_fields(value: Any, label: str = "inputs") -> None:
    leaked = find_forbidden_fields(value, label)
    if leaked:
        raise ContractValidationError(f"forbidden {label} fields detected: {leaked}")


def validate_schema_value(value: Any, schema: dict[str, Any], path: str) -> None:
    type_name = schema.get("type")
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
    }
    if type_name in checks and not checks[type_name](value):
        raise ContractValidationError(f"output schema type mismatch at {path}: {type_name}")
    if "const" in schema and value != schema["const"]:
        raise ContractValidationError(f"output schema const mismatch at {path}")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractValidationError(f"output schema enum mismatch at {path}")
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            raise ContractValidationError(f"output schema minLength mismatch at {path}")
        if schema.get("pattern") and re.fullmatch(str(schema["pattern"]), value) is None:
            raise ContractValidationError(f"output schema pattern mismatch at {path}")
    if isinstance(value, int) and not isinstance(value, bool) and "minimum" in schema:
        if value < int(schema["minimum"]):
            raise ContractValidationError(f"output schema minimum mismatch at {path}")
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
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                validate_schema_value(child, child_schema, f"{path}.{key}")


def validate_output(artifact: dict[str, Any], schema_name: str, label: str) -> None:
    schema = load_yaml_mapping(SCHEMA_ROOT / schema_name, f"{label} schema")
    validate_schema_value(artifact, schema, label)
    leaked = find_forbidden_fields(artifact, label)
    if leaked:
        raise ContractValidationError(f"forbidden output fields detected: {leaked}")


def stable_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path, chunk_size: int = HASH_CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def safe_repo_path(raw_path: str, base: Path, label: str) -> tuple[Path, str]:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ContractValidationError(f"{label} must be a non-empty path")
    normalized = raw_path.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if ".." in pure.parts:
        raise ContractValidationError(f"path traversal detected in {label}: {raw_path}")
    root = workspace_root().resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = base / Path(*pure.parts)
    resolved = candidate.expanduser().resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ContractValidationError(f"{label} escapes workspace: {raw_path}") from exc
    return resolved, relative.as_posix()


def canonical_source(source: str | Path, *, label: str = "source") -> str:
    if str(source).startswith("inline:"):
        return str(source)
    root = workspace_root().resolve()
    path = Path(source).expanduser()
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ContractValidationError(f"{label} escapes workspace: {source}") from exc


def version_key(value: Any) -> tuple[int, ...]:
    numbers = tuple(int(item) for item in re.findall(r"\d+", str(value)))
    return numbers or (0,)


def strictly_newer_version(previous: Any, current: Any) -> bool:
    return version_key(current) > version_key(previous)


def unique_sorted(values: Iterable[str]) -> list[str]:
    return sorted({str(value) for value in values})


validate_schema_value = canonical_validate_schema_value
