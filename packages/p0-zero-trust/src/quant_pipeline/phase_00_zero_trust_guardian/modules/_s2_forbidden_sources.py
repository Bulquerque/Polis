from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
import hashlib
import json
import re

import yaml

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._s2_common import normalized_version
from ._s2_forbidden_policy import (
    LINEAGE_PATTERN,
    SCHEMA_ID_PATTERN,
    contains_placeholder,
    context_mode,
    phase_ids_from_path,
    phase_ids_from_value,
    schema_phase_map,
)


def resolve_internal_path(value: Any, label: str, *, workspace_root: Path) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ContractValidationError(f"{label} must be a repository-relative POSIX path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        raise ContractValidationError(f"{label} contains path traversal: {value}")
    path = (workspace_root / Path(*pure.parts)).resolve()
    try:
        path.relative_to(workspace_root.resolve())
    except ValueError as exc:
        raise ContractValidationError(f"{label} is outside repository: {value}") from exc
    if not path.is_file():
        raise ContractValidationError(f"{label} does not exist: {value}")
    return path


def read_structured_path(path: Path, label: str) -> Any | None:
    lower = path.name.lower()
    try:
        if lower.endswith((".yaml", ".yml")):
            return yaml.safe_load(path.read_text(encoding="utf-8"))
        if lower.endswith(".json"):
            return json.loads(path.read_text(encoding="utf-8"))
        if lower.endswith(".jsonl"):
            return [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
    except (OSError, UnicodeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"invalid structured content for {label}: {exc}") from exc
    return None


def inline_document(entry: dict[str, Any]) -> Any | None:
    for key in ("document", "schema", "payload", "content"):
        if key in entry:
            value = entry[key]
            if not isinstance(value, (dict, list)):
                raise ContractValidationError(f"inline {key} must be a mapping or list")
            return value
    return None


def schema_sources(registry: dict[str, Any], *, workspace_root: Path, allow_global: bool = False) -> list[dict[str, Any]]:
    _validate_schema_registry_envelope(registry)
    phase_map = schema_phase_map(registry)
    seen: set[str] = set()
    sources: list[dict[str, Any]] = []
    for index, entry in enumerate(registry["schemas"]):
        if not isinstance(entry, dict):
            raise ContractValidationError(f"schema_registry entry {index} must be a mapping")
        schema_id = entry.get("schema_id")
        artifact_name = entry.get("artifact_name")
        if not isinstance(schema_id, str) or SCHEMA_ID_PATTERN.fullmatch(schema_id) is None:
            raise ContractValidationError(f"schema_registry entry {index} has invalid schema_id")
        if schema_id in seen:
            raise ContractValidationError(f"schema_registry contains duplicate schema_id: {schema_id}")
        if not isinstance(artifact_name, str) or not artifact_name.strip():
            raise ContractValidationError(f"schema_registry entry {index} has invalid artifact_name")
        seen.add(schema_id)
        path_value = entry.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            raise ContractValidationError(f"schema_registry entry {index} has invalid path")
        document = inline_document(entry)
        if document is None:
            path = resolve_internal_path(path_value, f"schema_registry path for {schema_id}", workspace_root=workspace_root)
            document = read_structured_path(path, schema_id)
            if not isinstance(document, dict):
                raise ContractValidationError(f"schema document must be a mapping: {schema_id}")
            declared_hash = entry.get("sha256")
            if declared_hash is not None and declared_hash != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ContractValidationError(f"schema_registry hash mismatch for {schema_id}")
        phases = _entry_phases(entry, path_value)
        phases.update(phase_map.get(path_value, set()))
        if not phases and allow_global:
            phases.add("GLOBAL")
        if not phases:
            raise ContractValidationError(f"schema_registry entry has no phase identity: {schema_id}")
        sources.append(
            {
                "source_kind": "schema",
                "source_id": schema_id,
                "schema_id": schema_id,
            "phases": sorted(phases, key=lambda item: (0, 0) if item == "GLOBAL" else (1, int(item[1:]))),
                "document": document,
                "mode": context_mode(entry, document, f"{schema_id} {artifact_name} {path_value}"),
            }
        )
    return sources


def _validate_schema_registry_envelope(registry: dict[str, Any]) -> None:
    if contains_placeholder(registry):
        raise ContractValidationError("schema_registry contains a symbolic placeholder")
    artifact_id = registry.get("artifact_id")
    if not isinstance(artifact_id, str) or re.fullmatch(r"schema-registry-[0-9a-f]{12}", artifact_id) is None:
        raise ContractValidationError("schema_registry artifact_id is invalid")
    if normalized_version(registry.get("pipeline_version")) != normalized_version(PIPELINE_VERSION):
        raise ContractValidationError("schema_registry pipeline version is incompatible")
    if LINEAGE_PATTERN.fullmatch(str(registry.get("lineage_id"))) is None:
        raise ContractValidationError("schema_registry lineage_id is invalid")
    if registry.get("promotion_blocked") is not True:
        raise ContractValidationError("schema_registry must remain promotion_blocked")
    schemas = registry.get("schemas")
    if not isinstance(schemas, list) or not schemas:
        raise ContractValidationError("schema_registry schemas must be non-empty")


def artifact_sources(registry: dict[str, Any], *, workspace_root: Path) -> list[dict[str, Any]]:
    if contains_placeholder(registry):
        raise ContractValidationError("artifact_registry contains a symbolic placeholder")
    artifacts = registry.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ContractValidationError("artifact_registry artifacts must be non-empty")
    seen: set[str] = set()
    sources: list[dict[str, Any]] = []
    for index, entry in enumerate(artifacts):
        if not isinstance(entry, dict):
            raise ContractValidationError(f"artifact_registry entry {index} must be a mapping")
        artifact_id = entry.get("artifact_id")
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            raise ContractValidationError(f"artifact_registry entry {index} has invalid artifact_id")
        if artifact_id in seen:
            raise ContractValidationError(f"artifact_registry contains duplicate artifact_id: {artifact_id}")
        seen.add(artifact_id)
        path_value = entry.get("path")
        document = inline_document(entry)
        if document is None:
            path = resolve_internal_path(path_value, f"artifact_registry path for {artifact_id}", workspace_root=workspace_root)
            document = read_structured_path(path, artifact_id)
        elif path_value is not None and not isinstance(path_value, str):
            raise ContractValidationError(f"artifact_registry path is invalid for {artifact_id}")
        phases = _entry_phases(entry, str(path_value or artifact_id))
        if not phases:
            raise ContractValidationError(f"artifact_registry entry has no phase identity: {artifact_id}")
        if document is None:
            continue
        sources.append(
            {
                "source_kind": "artifact",
                "source_id": artifact_id,
                "schema_id": str(entry.get("schema_id") or "not_applicable"),
                "phases": sorted(phases, key=lambda item: int(item[1:])),
                "document": document,
                "mode": context_mode(entry, document, f"{artifact_id} {path_value or ''}"),
            }
        )
    return sources


def _entry_phases(entry: dict[str, Any], path_value: str) -> set[str]:
    explicit = entry.get("phase_ids", entry.get("phase_id"))
    phases = phase_ids_from_value(explicit) if explicit is not None else set()
    phases.update(phase_ids_from_path(path_value))
    return phases
