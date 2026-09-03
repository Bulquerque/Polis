from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Iterator

from ._module_executor import ContractValidationError, _stable_digest


TASK_STATES = {
    "PLANNED",
    "RUNNING",
    "SUCCESS",
    "PARTIAL",
    "FAILED_BLOCKING",
    "FAILED_NON_BLOCKING",
    "RATE_LIMITED",
    "QUOTA_EXHAUSTED",
    "UNAVAILABLE",
    "SKIPPED",
    "NOT_APPLICABLE",
}

DEFAULT_CHUNK_SIZE = 1024 * 1024


def is_optional_source(value: dict | None) -> bool:
    """Return whether an explicitly non-canonical source may be absent.

    Missing data from these sources is a routing decision, not an ingestion
    failure.  Invalid bytes from a canonical source still go through the
    normal blocking/readability path.
    """
    if not isinstance(value, dict):
        return False
    role = str(value.get("authority_role") or "").strip().lower()
    return bool(
        value.get("optional") is True
        or value.get("required") is False
        or value.get("required_for_closure") is False
        or role in {"secondary", "optional"}
    )


def stable_id(prefix: str, payload: Any, *, length: int = 20) -> str:
    return f"{prefix}-{_stable_digest(payload)[:length]}"


def normalize_optional(value: Any) -> Any:
    return None if value in ("", None) else value


def derive_capture_id(record: dict, index: int = 0) -> str:
    existing = normalize_optional(record.get("capture_id"))
    if existing:
        return str(existing)
    identity = {
        "source_id": record.get("source_id"),
        "dataset_id": record.get("dataset_id") or record.get("dataset"),
        "task_id": record.get("task_id"),
        "request_id": record.get("request_id"),
        "partition_id": record.get("partition_id"),
        "page_id": record.get("page_id"),
        "lineage_id": record.get("lineage_id"),
        "index": index,
    }
    return stable_id("capture", identity)


def derive_raw_artifact_id(record: dict, capture_id: str) -> str:
    existing = normalize_optional(record.get("raw_artifact_id") or record.get("artifact_id"))
    if existing and not str(existing).startswith(("raw-file-inventory-", "raw-artifact-store-")):
        return str(existing)
    return stable_id("raw", {"capture_id": capture_id, "source_id": record.get("source_id")})


def derive_snapshot_id(record: dict, run_id: str | None = None) -> str:
    existing = normalize_optional(record.get("snapshot_id"))
    if existing:
        return str(existing)
    payload = {
        "run_id": run_id,
        "source_id": record.get("source_id"),
        "dataset_id": record.get("dataset_id") or record.get("dataset"),
        "task_id": record.get("task_id"),
        "request_id": record.get("request_id"),
        "capture_id": record.get("capture_id"),
        "partition_id": record.get("partition_id"),
        "page_id": record.get("page_id"),
        "raw_artifact_id": record.get("raw_artifact_id") or record.get("artifact_id"),
        "file_hash": record.get("file_hash"),
    }
    return stable_id("snapshot", payload)


def raw_path_from_record(record: dict) -> Path | None:
    """Return the first existing raw path without materializing its bytes."""
    for key in ("artifact_path", "raw_artifact_path", "source_file_path", "file_path"):
        value = normalize_optional(record.get(key))
        if value is None:
            continue
        path = Path(str(value))
        if path.is_file():
            return path
    return None


def iter_raw_chunks(record: dict, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> Iterator[bytes]:
    path = raw_path_from_record(record)
    if path is not None:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        return

    raw = record.get("raw_bytes")
    if isinstance(raw, bytes):
        if raw:
            yield raw
        return
    if isinstance(raw, bytearray):
        payload = bytes(raw)
        if payload:
            yield payload
        return
    if raw is not None:
        raise ContractValidationError("raw payload must remain bytes; parsed Python objects are not valid raw evidence")
    text = record.get("raw_text")
    if isinstance(text, str):
        payload = text.encode("utf-8")
        if payload:
            yield payload
        return
    raise ContractValidationError("raw artifact bytes are unavailable")


def raw_bytes_from_record(record: dict) -> bytes:
    """Compatibility helper. Prefer iter_raw_chunks for large artifacts."""
    return b"".join(iter_raw_chunks(record))


def raw_size(record: dict) -> int:
    path = raw_path_from_record(record)
    if path is not None:
        return path.stat().st_size
    raw = record.get("raw_bytes")
    if isinstance(raw, (bytes, bytearray)):
        return len(raw)
    text = record.get("raw_text")
    if isinstance(text, str):
        return len(text.encode("utf-8"))
    raise ContractValidationError("raw artifact bytes are unavailable")


def raw_prefix(record: dict, limit: int = 8192) -> bytes:
    path = raw_path_from_record(record)
    if path is not None:
        with path.open("rb") as handle:
            return handle.read(limit)
    raw = record.get("raw_bytes")
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw[:limit])
    text = record.get("raw_text")
    if isinstance(text, str):
        return text.encode("utf-8")[:limit]
    raise ContractValidationError("raw artifact bytes are unavailable")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_record(record: dict, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    for chunk in iter_raw_chunks(record, chunk_size=chunk_size):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def index_records(records: Iterable[dict], *keys: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in keys:
            value = normalize_optional(record.get(key))
            if value is not None:
                result.setdefault(str(value), record)
    return result


def records_for_task(records: Iterable[dict], task: dict) -> list[dict]:
    task_id = normalize_optional(task.get("task_id"))
    source_id = normalize_optional(task.get("source_id"))
    if task_id is not None:
        matched = [r for r in records if isinstance(r, dict) and str(r.get("task_id")) == str(task_id)]
        if matched:
            return matched
    # Legacy compatibility only when one task/source mapping exists.
    return [r for r in records if isinstance(r, dict) and source_id is not None and str(r.get("source_id")) == str(source_id)]


def find_related_record(records: Iterable[dict], record: dict) -> dict | None:
    for key in ("snapshot_id", "raw_artifact_id", "artifact_id", "capture_id", "task_id"):
        value = normalize_optional(record.get(key))
        if value is None:
            continue
        for candidate in records:
            if isinstance(candidate, dict) and str(candidate.get(key)) == str(value):
                return candidate
    source_id = normalize_optional(record.get("source_id"))
    if source_id is not None:
        candidates = [c for c in records if isinstance(c, dict) and str(c.get("source_id")) == str(source_id)]
        if len(candidates) == 1:
            return candidates[0]
    return None


def source_registry_map(source_registry: dict) -> dict[str, dict]:
    sources = source_registry.get("sources", []) if isinstance(source_registry, dict) else []
    return {
        str(item["source_id"]): item
        for item in sources
        if isinstance(item, dict) and item.get("source_id")
    }


def resolve_run_id(config: dict, manifest: dict | None = None, records: Iterable[dict] | None = None) -> str | None:
    # The run declared by the phase inputs is authoritative. Runtime config is
    # only a fallback for direct module/unit execution. This prevents a generic
    # test/config value from overwriting the actual ingestion run identity.
    if isinstance(manifest, dict):
        value = normalize_optional(manifest.get("ingestion_run_id") or manifest.get("run_id"))
        if value:
            return str(value)
    for record in records or []:
        if not isinstance(record, dict):
            continue
        value = normalize_optional(record.get("ingestion_run_id") or record.get("run_id"))
        if value:
            return str(value)
    for key in ("ingestion_run_id", "run_id"):
        value = normalize_optional(config.get(key))
        if value:
            return str(value)
    return None


def json_structure(payload: bytes) -> tuple[list[str] | None, int | None]:
    obj = json.loads(payload.decode("utf-8"))
    return json_structure_from_object(obj)


def json_structure_from_object(obj: Any) -> tuple[list[str] | None, int | None]:
    if isinstance(obj, dict):
        return sorted(str(k) for k in obj.keys()), len(obj)
    if isinstance(obj, list):
        keys: set[str] = set()
        for item in obj[:50]:
            if isinstance(item, dict):
                keys.update(str(k) for k in item.keys())
        return sorted(keys) or None, len(obj)
    return None, 1
