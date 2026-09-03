from __future__ import annotations

from typing import Any
import hashlib
import json
import re
from datetime import datetime, timezone

import yaml

from ._module_executor import ContractValidationError, PIPELINE_VERSION, SCHEMA_ROOT
from ..validators import FORBIDDEN_ECONOMIC_FIELDS, normalize_field_name

FORBIDDEN = set(FORBIDDEN_ECONOMIC_FIELDS)
LINEAGE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PHASE_RE = re.compile(r"^P\d+$")
MODULE_RE = re.compile(r"^(P\d+)(?:\.S\d+)?(?:\.M\d+)?$")
SEVERITIES = {"CRITICAL", "ERROR", "WARNING", "NOTICE", "INFO"}
CONDITIONS = {
    "FAILURE",
    "INCOMPLETE",
    "NOT_STARTED",
    "MISSING_EVIDENCE",
    "STALE",
    "CONFLICT",
    "INTEGRITY_FAILURE",
    "TEST_FAILURE",
    "POLICY_VIOLATION",
    "QUALIFICATION_FAILURE",
    "QUALIFICATION_INCOMPLETE",
}
BLOCK = "BLOCKS_READINESS"
NO_BLOCK = "DOES_NOT_BLOCK_READINESS"
RELEASE_BLOCK = "BLOCKS_RELEASE"
NO_RELEASE_BLOCK = "DOES_NOT_BLOCK_RELEASE"


def created_at(config: dict[str, Any]) -> str:
    value = config.get("created_at") or config.get("generated_at") or config.get("evaluation_time")
    if value:
        return str(value)
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def scan(value: Any, path: str = "inputs") -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if normalize_field_name(key) in {normalize_field_name(field) for field in FORBIDDEN}:
                result.append(child_path)
            result.extend(scan(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(scan(child, f"{path}[{index}]"))
    return result


def require(inputs: Any, config: Any, names: list[str]) -> dict[str, Any]:
    if not isinstance(inputs, dict):
        raise ContractValidationError("inputs must be a dict")
    if config is not None and not isinstance(config, dict):
        raise ContractValidationError("config must be a dict")
    missing = [name for name in names if name not in inputs]
    if missing:
        raise ContractValidationError(f"missing required inputs: {missing}")
    leaked = scan(inputs)
    if leaked:
        raise ContractValidationError(f"forbidden input fields detected: {leaked}")
    return {} if config is None else config


def artifact(value: Any, name: str) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("outputs"), dict):
        value = value["outputs"].get(name)
    if not isinstance(value, dict):
        raise ContractValidationError(f"{name} must be a material artifact mapping")
    return value


def lineage(value: dict[str, Any], label: str) -> str:
    result = value.get("lineage_id")
    if not isinstance(result, str) or LINEAGE_RE.fullmatch(result) is None:
        raise ContractValidationError(f"{label} has invalid lineage_id")
    if not isinstance(value.get("artifact_id"), str) or not value["artifact_id"]:
        raise ContractValidationError(f"{label} has no artifact_id")
    return result


def digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_output(value: dict[str, Any], filename: str) -> None:
    schema = yaml.safe_load((SCHEMA_ROOT / filename).read_text(encoding="utf-8")) or {}
    missing = [key for key in schema.get("required_fields", []) if key not in value]
    if missing:
        raise ContractValidationError(f"{filename} output missing fields: {missing}")
    leaked = scan(value, filename)
    if leaked:
        raise ContractValidationError(f"forbidden output fields detected: {leaked}")


def envelope(module_id: str, name: str, inputs: list[str], outputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "module_id": module_id,
        "module_name": name,
        "phase": "P0",
        "subphase": "P0.S9",
        "contract": f"{module_id.replace('.', '_')}_{name}.yaml",
        "required_inputs": inputs,
        "outputs": outputs,
    }
