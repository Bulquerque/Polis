from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
import hashlib
import json
import unicodedata
from datetime import datetime, timezone

import yaml

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ..validators import FORBIDDEN_ECONOMIC_FIELDS, normalize_field_name

PACKAGE_ROOT = Path(__file__).resolve().parents[4]
REPOSITORY_ROOT = Path(__file__).resolve().parents[6]
PERMISSION_NAMES = ("read", "write", "execute", "network", "delegate")
FORBIDDEN_FIELDS = set(FORBIDDEN_ECONOMIC_FIELDS)


def created_at(config: dict[str, Any]) -> str:
    value = config.get("created_at") or config.get("evaluation_time") or config.get("generated_at")
    if not value:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return str(value)


def digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def reject_forbidden(value: Any, path: str = "inputs") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if normalize_field_name(key) in {normalize_field_name(field) for field in FORBIDDEN_FIELDS}:
                raise ContractValidationError(f"forbidden field at {path}.{key}")
            reject_forbidden(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_forbidden(child, f"{path}[{index}]")


def resolve_repository_path(value: Any, label: str) -> tuple[Path, str]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ContractValidationError(f"{label} must be a repository-relative POSIX path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        raise ContractValidationError(f"{label} contains path traversal")

    candidates = [REPOSITORY_ROOT.resolve(), PACKAGE_ROOT.resolve()]
    for root in candidates:
        path = (root / Path(*pure.parts)).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            continue
        if path.is_file():
            return path, pure.as_posix()
    raise ContractValidationError(f"{label} does not exist: {value}")


def load_mapping(value: Any, label: str) -> tuple[dict[str, Any], str, str]:
    if isinstance(value, dict) and "path" not in value:
        return value, f"inline:{label}", digest(value)
    candidate = value.get("path") if isinstance(value, dict) else value
    path, relative = resolve_repository_path(candidate, label)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ContractValidationError(f"invalid YAML for {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractValidationError(f"{label} must be a mapping")
    return data, relative, hashlib.sha256(path.read_bytes()).hexdigest()


def load_document(value: Any, label: str) -> tuple[Any, str, str]:
    if isinstance(value, (dict, list)) and not (isinstance(value, dict) and "path" in value):
        return value, f"inline:{label}", digest(value)
    candidate = value.get("path") if isinstance(value, dict) else value
    path, relative = resolve_repository_path(candidate, label)
    raw = path.read_text(encoding="utf-8")
    parsed: Any
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError:
        parsed = raw
    return parsed, relative, hashlib.sha256(path.read_bytes()).hexdigest()


def load_local_spec(filename: str) -> tuple[dict[str, Any], str]:
    root = Path(__file__).resolve().parents[4]
    path = root / "contracts" / filename
    if not path.is_file():
        raise ContractValidationError(f"missing local S7 policy: {filename}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ContractValidationError(f"invalid local S7 policy: {filename}")
    return data, hashlib.sha256(path.read_bytes()).hexdigest()


def list_field(data: dict[str, Any], field: str, label: str) -> list[dict[str, Any]]:
    value = data.get(field)
    if not isinstance(value, list) or not value or not all(isinstance(item, dict) for item in value):
        raise ContractValidationError(f"{label}.{field} must be a non-empty list of mappings")
    return value


def ensure_unique(items: list[dict[str, Any]], field: str, label: str) -> None:
    values = [item.get(field) for item in items]
    if not all(isinstance(value, str) and value for value in values):
        raise ContractValidationError(f"{label}.{field} must contain non-empty strings")
    if len(values) != len(set(values)):
        raise ContractValidationError(f"{label}.{field} values must be unique")


def validate_upstream(value: dict[str, Any], label: str) -> None:
    materialized = any(
        key in value
        for key in ("artifact_id", "lineage_id", "pipeline_version", "status", "release_blocking")
    )
    if not materialized:
        return
    required = {"artifact_id", "lineage_id", "pipeline_version"}
    if required.difference(value):
        raise ContractValidationError(f"{label} has incomplete trust metadata")
    if value["pipeline_version"] != PIPELINE_VERSION:
        raise ContractValidationError(f"{label} pipeline_version is incompatible")
    if value.get("status", "PASS") not in {"PASS", "QUALIFIED"}:
        raise ContractValidationError(f"{label} is release-blocking")
    if value.get("blocking") is True or value.get("release_blocking") is True:
        raise ContractValidationError(f"{label} is release-blocking")
    lineage = value["lineage_id"]
    artifact_id = value["artifact_id"]
    if not isinstance(lineage, str) or not lineage.startswith("sha256:") or len(lineage) != 71:
        raise ContractValidationError(f"{label} lineage_id is malformed")
    if not isinstance(artifact_id, str) or not artifact_id.endswith(lineage[7:19]):
        raise ContractValidationError(f"{label} artifact identity does not match lineage")


def permission_map(value: Any, label: str) -> dict[str, bool]:
    if isinstance(value, list):
        if not value or not all(isinstance(item, str) and item in PERMISSION_NAMES for item in value):
            raise ContractValidationError(f"{label} permissions invalid")
        return {name: name in set(value) for name in PERMISSION_NAMES}
    if isinstance(value, dict):
        if set(value).difference(PERMISSION_NAMES) or not all(isinstance(v, bool) for v in value.values()):
            raise ContractValidationError(f"{label} permissions invalid")
        return {name: bool(value.get(name, False)) for name in PERMISSION_NAMES}
    raise ContractValidationError(f"{label} permissions invalid")


def permission_names(value: dict[str, bool]) -> list[str]:
    return [name for name in PERMISSION_NAMES if value.get(name) is True]


def validate_relative_paths(paths: Any, label: str) -> list[str]:
    if not isinstance(paths, list) or not paths:
        raise ContractValidationError(f"{label} must be a non-empty list")
    normalized: list[str] = []
    for item in paths:
        if not isinstance(item, str) or not item or "\\" in item:
            raise ContractValidationError(f"{label} contains invalid path")
        pure = PurePosixPath(item)
        if pure.is_absolute() or ".." in pure.parts:
            raise ContractValidationError(f"{label} contains unsafe path")
        normalized.append(pure.as_posix())
    return sorted(set(normalized))


def envelope(
    module_id: str,
    name: str,
    contract: str,
    required: list[str],
    output_name: str,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    reject_forbidden(artifact, output_name)
    return {
        "module_id": module_id,
        "module_name": name,
        "phase": "P0",
        "subphase": "P0.S7",
        "contract": contract,
        "required_inputs": required,
        "outputs": {output_name: artifact},
    }
