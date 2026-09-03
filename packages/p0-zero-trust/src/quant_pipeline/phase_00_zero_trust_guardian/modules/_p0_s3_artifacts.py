from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import csv
import io

import yaml

from ._module_executor import ContractValidationError
from ._p0_s3_shared import (
    CANONICAL_HASH_ALGORITHM,
    SHA256_RE,
    canonical_source,
    find_forbidden_fields,
    load_yaml_mapping,
    safe_repo_path,
    sha256_file,
    workspace_root,
)


@dataclass(frozen=True)
class ArtifactRecord:
    source: str
    path: str
    resolved_path: Path
    algorithm: str
    declared_hash: str
    artifact_id: str
    producer_module_id: str
    parents: tuple[str, ...]
    schema_version: str
    mutability_class: str
    critical: bool
    raw: dict[str, Any]

    @property
    def stable_identity(self) -> bool:
        return bool(self.raw.get("artifact_id") or self.raw.get("identity"))


def mapping_or_path(value: Any, label: str) -> tuple[dict[str, Any], str]:
    if isinstance(value, dict) and "path" not in value:
        return value, f"inline:{label}"
    candidate: str | None = None
    if isinstance(value, (str, Path)):
        candidate = str(value)
    elif isinstance(value, dict) and isinstance(value.get("path"), str):
        candidate = value["path"]
    if not candidate:
        raise ContractValidationError(f"{label} must be a mapping or internal YAML path")
    root = workspace_root()
    path, _ = safe_repo_path(candidate, root, label)
    return load_yaml_mapping(path, label.replace("_", " ")), canonical_source(path, label=label)


def manifest_sources(value: Any) -> list[Any]:
    if isinstance(value, (str, Path)):
        return [value]
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if isinstance(value.get("manifests"), list):
            return value["manifests"]
        if isinstance(value.get("artifacts"), list):
            return [value]
    raise ContractValidationError("artifact manifest collection must contain manifests or artifacts")


def _read_manifest_path(value: str | Path) -> tuple[list[dict[str, Any]], Path, str]:
    root = workspace_root()
    path, _ = safe_repo_path(str(value), root, "artifact manifest")
    if not path.is_file():
        raise ContractValidationError(f"artifact manifest does not exist: {path}")
    try:
        content = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".csv":
            reader = csv.DictReader(io.StringIO(content))
            if reader.fieldnames is None or not {"path", "sha256"}.issubset(reader.fieldnames):
                raise ContractValidationError(f"artifact manifest CSV lacks path/sha256 columns: {path}")
            records = [dict(row) for row in reader]
        else:
            document = yaml.safe_load(content)
            if not isinstance(document, dict) or not isinstance(document.get("artifacts"), list):
                raise ContractValidationError(f"artifact manifest YAML is malformed: {path}")
            records = document["artifacts"]
    except (OSError, UnicodeError, csv.Error, yaml.YAMLError) as exc:
        raise ContractValidationError(f"artifact manifest is malformed: {path}: {exc}") from exc
    if not records or not all(isinstance(record, dict) for record in records):
        raise ContractValidationError(f"artifact manifest has no record mappings: {path}")
    return records, path.parent, canonical_source(path, label="artifact manifest")


def manifest_documents(value: Any) -> list[tuple[list[dict[str, Any]], Path, str]]:
    documents: list[tuple[list[dict[str, Any]], Path, str]] = []
    root = workspace_root()
    for index, source in enumerate(manifest_sources(value)):
        if isinstance(source, (str, Path)):
            documents.append(_read_manifest_path(source))
            continue
        if isinstance(source, dict) and isinstance(source.get("path"), str) and "artifacts" not in source:
            documents.append(_read_manifest_path(source["path"]))
            continue
        if not isinstance(source, dict) or not isinstance(source.get("artifacts"), list):
            raise ContractValidationError(f"artifact manifest source {index} is malformed")
        records = source["artifacts"]
        if not records or not all(isinstance(record, dict) for record in records):
            raise ContractValidationError(f"inline artifact manifest {index} has no record mappings")
        base_value = source.get("base_path")
        base = root if base_value is None else safe_repo_path(str(base_value), root, f"inline manifest base {index}")[0]
        documents.append((records, base, f"inline:artifact_manifest_all_phases[{index}]"))
    if not documents:
        raise ContractValidationError("artifact manifest collection is empty")
    return documents


def entry_hash(record: dict[str, Any]) -> tuple[str, str]:
    algorithm = record.get("algorithm") or record.get("hash_algorithm")
    expected = record.get("sha256")
    if expected not in (None, ""):
        algorithm = algorithm or CANONICAL_HASH_ALGORITHM
    else:
        expected = record.get("hash") or record.get("digest") or ""
    if isinstance(expected, str) and expected.lower().startswith("sha256:"):
        algorithm = algorithm or CANONICAL_HASH_ALGORITHM
        expected = expected.split(":", 1)[1]
    return str(algorithm or CANONICAL_HASH_ALGORITHM).lower().replace("-", ""), str(expected or "").lower()


def _parents(record: dict[str, Any]) -> tuple[str, ...]:
    value = record.get("parents", record.get("parent_artifacts", []))
    if value in (None, ""):
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ContractValidationError("artifact parents must be a list of non-empty artifact identities")
    return tuple(value)


def _mutability_class(record: dict[str, Any], relative_path: str) -> str:
    explicit = str(record.get("mutability_class") or "").upper().strip()
    if explicit:
        allowed = {"IMMUTABLE", "APPEND_ONLY", "VERSIONED", "REPLACEABLE", "EPHEMERAL"}
        if explicit not in allowed:
            raise ContractValidationError(f"unsupported mutability_class: {explicit}")
        return explicit
    artifact_type = str(record.get("artifact_type") or record.get("type") or "").lower()
    if artifact_type == "raw" or "raw" in Path(relative_path).parts:
        return "IMMUTABLE"
    if relative_path.endswith(".schema.yaml"):
        return "VERSIONED"
    return "REPLACEABLE"


def artifact_record(record: dict[str, Any], base: Path, source: str) -> ArtifactRecord:
    leaked = find_forbidden_fields(record, source)
    if leaked:
        raise ContractValidationError(f"forbidden manifest fields detected: {leaked}")
    raw_path = next((record.get(key) for key in ("path", "artifact_path", "file_path") if record.get(key)), None)
    if not isinstance(raw_path, str):
        raise ContractValidationError(f"artifact path is missing in {source}")
    resolved, relative = safe_repo_path(raw_path, base, "artifact path")
    algorithm, declared_hash = entry_hash(record)
    identity = record.get("artifact_id") or record.get("identity") or relative
    if not isinstance(identity, str) or not identity.strip():
        raise ContractValidationError(f"artifact identity is malformed in {source}")
    producer = record.get("producer_module_id") or record.get("producer") or ""
    if producer is not None and not isinstance(producer, str):
        raise ContractValidationError("artifact producer must be a string")
    schema_version = str(record.get("schema_version") or "")
    critical = record.get("critical") is True or str(record.get("criticality", "")).upper() == "CRITICAL"
    return ArtifactRecord(
        source=source,
        path=relative,
        resolved_path=resolved,
        algorithm=algorithm,
        declared_hash=declared_hash,
        artifact_id=identity,
        producer_module_id=str(producer or ""),
        parents=_parents(record),
        schema_version=schema_version,
        mutability_class=_mutability_class(record, relative),
        critical=critical,
        raw=dict(record),
    )


def artifact_records(value: Any) -> tuple[list[ArtifactRecord], list[str]]:
    records: list[ArtifactRecord] = []
    sources: list[str] = []
    for raw_records, base, source in manifest_documents(value):
        sources.append(source)
        records.extend(artifact_record(record, base, source) for record in raw_records)
    return records, sorted(set(sources))


def registry_records(value: Any) -> tuple[list[dict[str, Any]], str]:
    document, source = mapping_or_path(value, "artifact_registry")
    records = document.get("artifacts")
    if not isinstance(records, list) or not records or not all(isinstance(item, dict) for item in records):
        raise ContractValidationError("artifact_registry must contain non-empty artifact mappings")
    leaked = find_forbidden_fields(document, "artifact_registry")
    if leaked:
        raise ContractValidationError(f"forbidden artifact registry fields detected: {leaked}")
    return records, source


def validate_digest(record: ArtifactRecord) -> tuple[str, str]:
    if record.algorithm != CANONICAL_HASH_ALGORITHM:
        return "DISALLOWED_ALGORITHM", ""
    if SHA256_RE.fullmatch(record.declared_hash) is None:
        return "MISSING_HASH", ""
    if not record.resolved_path.is_file():
        return "MISSING_FILE", ""
    actual = sha256_file(record.resolved_path)
    if actual != record.declared_hash:
        return "HASH_MISMATCH", actual
    return "PASS", actual
