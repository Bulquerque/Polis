from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Callable
import csv
import hashlib
import io
import json
import re

import yaml

from ._module_executor import ContractValidationError


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
FORMAT_INSPECTORS: dict[str, str] = {
    "yaml": "yaml",
    "schema.yaml": "schema_yaml",
    "json": "json",
    "jsonl": "jsonl",
    "csv": "csv",
    "md": "text",
    "mmd": "text",
    "png": "png",
    "parquet": "parquet",
}


def load_mapping_input(
    value: Any,
    collection: str,
    label: str,
    *,
    repository_root: Path,
    load_yaml: Callable[[Path, str], dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    if isinstance(value, dict) and isinstance(value.get(collection), list):
        return value, f"inline:{label}"
    candidate: str | None = None
    if isinstance(value, (str, Path)):
        candidate = str(value)
    elif isinstance(value, dict) and isinstance(value.get("path"), str):
        candidate = value["path"]
    if not candidate:
        raise ContractValidationError(f"{label} must be an inline mapping or explicit YAML path")
    path = Path(candidate).expanduser().resolve()
    try:
        path.relative_to(repository_root.resolve())
    except ValueError as exc:
        raise ContractValidationError(f"{label} path is outside repository: {path}") from exc
    mapping = load_yaml(path, label)
    if not isinstance(mapping.get(collection), list):
        raise ContractValidationError(f"{label} must contain {collection}")
    return mapping, path.as_posix()


def validate_policy(policy: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    formats = policy.get("formats")
    forbidden = policy.get("forbidden")
    if not isinstance(policy.get("policy_id"), str) or not policy["policy_id"]:
        raise ContractValidationError("artifact format policy_id must be non-empty")
    if not isinstance(formats, dict) or not formats:
        raise ContractValidationError("artifact format policy formats must be non-empty")
    if not isinstance(forbidden, list) or not forbidden:
        raise ContractValidationError("artifact format policy forbidden rules must be non-empty")
    if not all(isinstance(key, str) and key for key in formats):
        raise ContractValidationError("artifact format policy type names must be non-empty strings")
    if not all(isinstance(value, str) and value for value in formats.values()):
        raise ContractValidationError("artifact format policy contains malformed format values")
    unsupported = sorted(set(formats.values()) - set(FORMAT_INSPECTORS))
    if unsupported:
        raise ContractValidationError(
            f"artifact format policy references formats without validators: {unsupported}"
        )
    if not all(isinstance(item, str) and item for item in forbidden):
        raise ContractValidationError("artifact format policy forbidden rules are malformed")
    return dict(formats), list(forbidden)


def actual_format(path: Path) -> str:
    if path.name.lower().endswith(".schema.yaml"):
        return "schema.yaml"
    return path.suffix.lower().lstrip(".")


def inspect_content(path: Path, expected_format: str) -> str | None:
    inspector = FORMAT_INSPECTORS.get(expected_format)
    if inspector is None:
        return f"no content validator is implemented for {expected_format}"
    try:
        if inspector == "parquet":
            return _inspect_parquet(path)
        if inspector == "png":
            return _inspect_png(path)
        if inspector == "jsonl":
            return _inspect_jsonl(path)
        data = path.read_bytes()
    except OSError as exc:
        return f"artifact is unreadable: {exc}"
    if not data:
        return "artifact content is empty"
    try:
        if inspector == "yaml":
            parsed = yaml.safe_load(data.decode("utf-8"))
            if not isinstance(parsed, dict):
                return "YAML content must be a mapping"
        elif inspector == "schema_yaml":
            parsed = yaml.safe_load(data.decode("utf-8"))
            if not isinstance(parsed, dict):
                return "schema YAML content must be a mapping"
            if not (parsed.get("schema_id") or parsed.get("artifact_name") or parsed.get("type")):
                return "schema YAML does not declare schema identity or structure"
        elif inspector == "json":
            json.loads(data.decode("utf-8"))
        elif inspector == "csv":
            reader = csv.reader(io.StringIO(data.decode("utf-8-sig")))
            header = next(reader, None)
            if not header or not all(cell.strip() for cell in header):
                return "CSV content has no valid header"
        elif inspector == "text" and not data.decode("utf-8").strip():
            return "text artifact is empty"
    except (UnicodeError, json.JSONDecodeError, yaml.YAMLError, csv.Error) as exc:
        return f"content is incompatible with {expected_format}: {exc}"
    return None


def _inspect_parquet(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            start = handle.read(4)
            handle.seek(-4, 2)
            end = handle.read(4)
    except (OSError, ValueError) as exc:
        return f"artifact is unreadable: {exc}"
    if start != b"PAR1" or end != b"PAR1":
        return "Parquet magic bytes are invalid"
    return None


def _inspect_png(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            signature = handle.read(8)
    except OSError as exc:
        return f"artifact is unreadable: {exc}"
    return None if signature == b"\x89PNG\r\n\x1a\n" else "PNG signature is invalid"


def _inspect_jsonl(path: Path) -> str | None:
    seen = False
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                seen = True
                try:
                    json.loads(line)
                except json.JSONDecodeError as exc:
                    return f"content is incompatible with jsonl at line {line_number}: {exc}"
    except (OSError, UnicodeError) as exc:
        return f"artifact is unreadable: {exc}"
    return None if seen else "JSONL content has no records"


def forbidden_format_findings(
    *,
    artifact_id: str,
    artifact_type: str,
    path: str,
    actual: str,
    rules: list[str],
    finding_factory: Callable[[str, str, str, str, str, str], dict[str, str]],
) -> list[dict[str, str]]:
    parts = set(PurePosixPath(path).parts)
    findings: list[dict[str, str]] = []
    suffix = PurePosixPath(path).suffix.lower()
    if "pickle_for_cross_phase_artifacts" in rules and suffix in {".pkl", ".pickle"}:
        findings.append(
            finding_factory(
                artifact_id,
                path,
                "forbidden_pickle_artifact",
                "pickle is forbidden for cross-phase artifacts",
                "policy-approved portable format",
                actual,
            )
        )
    if "raw_excel_as_contract" in rules and suffix in {".xls", ".xlsx", ".xlsm"} and (
        "contracts" in parts or "modules" in parts or artifact_type == "contract"
    ):
        findings.append(
            finding_factory(
                artifact_id,
                path,
                "raw_excel_as_contract",
                "raw Excel files cannot be used as contracts",
                "yaml",
                actual,
            )
        )
    return findings



def resolve_internal_path(
    value: Any,
    label: str,
    *,
    repository_root: Path,
    must_exist: bool = True,
) -> tuple[Path, str]:
    from pathlib import PurePosixPath

    if not isinstance(value, str) or not value or "\\" in value:
        raise ContractValidationError(f"{label} must be a repository-relative POSIX path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        raise ContractValidationError(f"{label} contains path traversal: {value}")
    path = (repository_root / Path(*pure.parts)).resolve()
    try:
        path.relative_to(repository_root.resolve())
    except ValueError as exc:
        raise ContractValidationError(f"{label} is outside repository: {value}") from exc
    if must_exist and not path.is_file():
        raise ContractValidationError(f"{label} does not exist: {value}")
    return path, pure.as_posix()


def finding(
    artifact_id: str,
    path: str,
    code: str,
    message: str,
    expected_format: str,
    actual_format: str,
) -> dict[str, str]:
    return {
        "artifact_id": artifact_id,
        "path": path,
        "code": code,
        "severity": "blocking",
        "message": message,
        "expected_format": expected_format,
        "actual_format": actual_format,
    }

def artifact_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
