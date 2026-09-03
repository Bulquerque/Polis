from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
import hashlib
import json
import re
from datetime import datetime, timezone

import yaml

from ._module_executor import ContractValidationError, PIPELINE_VERSION, SCHEMA_ROOT, strict_json_bytes
from ._canonical_schema_validator import validate_schema_value
from ..validators import FORBIDDEN_ECONOMIC_FIELDS, normalize_field_name

FORBIDDEN_FIELDS = frozenset(FORBIDDEN_ECONOMIC_FIELDS)


def created_at(config: dict[str, Any]) -> str:
    value = config.get("created_at") or config.get("generated_at")
    if value:
        return str(value)
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def load_mapping(value: Any, label: str) -> dict[str, Any]:
    if isinstance(value, dict) and "path" not in value:
        if not value or set(value) == {"source"}:
            raise ContractValidationError(f"{label} is a symbolic placeholder")
        return value
    candidate = value if isinstance(value, (str, Path)) else value.get("path") if isinstance(value, dict) else None
    if not isinstance(candidate, (str, Path)) or not str(candidate).strip():
        raise ContractValidationError(f"{label} must be a materialized mapping or YAML path")
    return load_yaml_mapping(Path(candidate).expanduser().resolve(), label)


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


def normalize_repo_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{label} path is missing")
    normalized = value.replace("\\", "/")
    parsed = PurePosixPath(normalized)
    if parsed.is_absolute() or ".." in parsed.parts or normalized.startswith("/"):
        raise ContractValidationError(f"{label} path escapes repository: {value}")
    return parsed.as_posix()


def source_files(value: Any) -> list[dict[str, Any]]:
    raw = value.get("files") if isinstance(value, dict) else value
    if not isinstance(raw, list) or not raw:
        raise ContractValidationError("source_tree_manifest must contain a non-empty files list")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ContractValidationError(f"source_tree_manifest.files[{index}] must be a mapping")
        path = normalize_repo_path(item.get("path"), f"source_tree_manifest.files[{index}]")
        if path in seen:
            raise ContractValidationError(f"duplicate source path: {path}")
        content = item.get("content")
        if not isinstance(content, str):
            raise ContractValidationError(f"source content is not materialized: {path}")
        seen.add(path)
        result.append({"path": path, "content": content})
    return result


def digest_payload(payload: Any) -> str:
    blob = strict_json_bytes(payload)
    return hashlib.sha256(blob).hexdigest()


def envelope(name: str, payload: Any, config: dict[str, Any]) -> dict[str, Any]:
    digest = digest_payload(payload)
    return {
        "artifact_id": f"{name.replace('_', '-')}-{digest[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{digest}",
    }



def module_result(module_id: str, module_name: str, required: list[str], output_name: str, artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "module_id": module_id,
        "module_name": module_name,
        "phase": "P0",
        "subphase": "P0.S5",
        "contract": f"{module_id.replace('.', '_')}_{module_name}.yaml",
        "required_inputs": required,
        "outputs": {output_name: artifact},
    }
