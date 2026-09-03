from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
import hashlib
import json
import re
from datetime import datetime, timezone

import yaml

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ..validators import FORBIDDEN_ECONOMIC_FIELDS, normalize_field_name

REPOSITORY_ROOT = Path(__file__).resolve().parents[6]
FORBIDDEN_FIELDS = set(FORBIDDEN_ECONOMIC_FIELDS)
_LINEAGE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ALLOWED_STATUS = {
    "PASS",
    "FAIL",
    "BLOCKED",
    "APPROVED",
    "READY",
    "NOT_READY",
    "PHASE_QUALIFIED",
    "QUALIFICATION_FAILED",
    "NOT_EVALUATED",
    "OUT_OF_SCOPE",
    "EXTERNAL_UNAVAILABLE",
}


def created_at(config: dict[str, Any]) -> str:
    value = config.get("created_at") or config.get("evaluation_time") or config.get("generated_at")
    if value:
        return str(value)
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def reject_forbidden(value: Any, path: str = "inputs") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if normalize_field_name(key) in {normalize_field_name(field) for field in FORBIDDEN_FIELDS}:
                raise ContractValidationError(f"forbidden field at {path}.{key}")
            reject_forbidden(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_forbidden(child, f"{path}[{index}]")


def mapping(value: Any, label: str) -> tuple[dict[str, Any], str, str]:
    if isinstance(value, dict) and "path" not in value:
        return value, f"inline:{label}", digest(value)
    candidate = value.get("path") if isinstance(value, dict) else value
    path, source = _safe_repository_path(candidate, label)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ContractValidationError(f"invalid document for {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractValidationError(f"{label} must contain a mapping")
    return data, source, hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(
    value: Any,
    label: str,
    *,
    require_current_version: bool = True,
) -> tuple[dict[str, Any], str, str]:
    data, source, source_hash = mapping(value, label)
    reject_forbidden(data, label)
    _validate_identity(data, label)
    if require_current_version:
        _validate_current_version(data, label)
    _validate_gate_fields(data, label)
    return data, source, source_hash


def is_blocking(data: dict[str, Any]) -> bool:
    return (
        data.get("status") in {"FAIL", "BLOCKED"}
        or data.get("release_blocking") is True
        or data.get("blocking") is True
    )


def envelope(
    module_id: str,
    name: str,
    contract: str,
    required: list[str],
    output_name: str,
    output: dict[str, Any],
) -> dict[str, Any]:
    reject_forbidden(output, output_name)
    return {
        "module_id": module_id,
        "module_name": name,
        "phase": "P0",
        "subphase": "P0.S8",
        "contract": contract,
        "required_inputs": required,
        "outputs": {output_name: output},
    }


def source_record(label: str, data: dict[str, Any], source: str, source_hash: str) -> dict[str, Any]:
    return {
        "artifact_name": label,
        "artifact_id": data["artifact_id"],
        "lineage_id": data["lineage_id"],
        "source_path": source,
        "source_sha256": source_hash,
    }


def promotion_allowed(config: dict[str, Any]) -> bool:
    return config.get("production_promotion_allowed") is True


def _safe_repository_path(candidate: Any, label: str) -> tuple[Path, str]:
    if not isinstance(candidate, str) or not candidate or "\\" in candidate:
        raise ContractValidationError(f"{label} must be a mapping or repository-relative POSIX path")
    pure = PurePosixPath(candidate)
    if pure.is_absolute() or ".." in pure.parts:
        raise ContractValidationError(f"{label} contains path traversal")
    path = (REPOSITORY_ROOT / Path(*pure.parts)).resolve()
    try:
        path.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError as exc:
        raise ContractValidationError(f"{label} escapes repository") from exc
    if not path.is_file():
        raise ContractValidationError(f"{label} does not exist: {candidate}")
    return path, pure.as_posix()


def _validate_identity(data: dict[str, Any], label: str) -> None:
    missing = [
        key
        for key in ("artifact_id", "pipeline_version", "lineage_id")
        if not isinstance(data.get(key), str) or not data.get(key)
    ]
    if missing:
        raise ContractValidationError(f"{label} lacks material identity fields: {missing}")
    if not _LINEAGE.fullmatch(data["lineage_id"]):
        raise ContractValidationError(f"{label}.lineage_id is not a SHA-256 lineage")


def _validate_current_version(data: dict[str, Any], label: str) -> None:
    from ._s8_version_model import parse_version

    observed = parse_version(data["pipeline_version"], label=f"{label}.pipeline_version")
    expected = parse_version(PIPELINE_VERSION, label="PIPELINE_VERSION")
    if observed != expected:
        raise ContractValidationError(f"{label}.pipeline_version is incompatible")


def _validate_gate_fields(data: dict[str, Any], label: str) -> None:
    for key in ("release_blocking", "blocking"):
        if key in data and not isinstance(data[key], bool):
            raise ContractValidationError(f"{label}.{key} must be boolean")
    if "status" in data:
        status = str(data["status"]).upper()
        if status not in _ALLOWED_STATUS:
            raise ContractValidationError(f"{label}.status is invalid")
