from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import tempfile

from ._module_executor import ContractValidationError, _stable_digest
from ..core import identity_digest
from ._p1_semantic_helpers import records_from_artifact, validate_inputs
from ._s345_semantics import (
    derive_capture_id,
    derive_raw_artifact_id,
    iter_raw_chunks,
    raw_path_from_record,
    sha256_record,
)


def _safe(value: object, fallback: str = "unknown") -> str:
    text = str(value or fallback)
    return re.sub(r"[^A-Za-z0-9._-]", "_", text)


def _sha256_path(path: Path, chunk_size: int = 1024 * 1024) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _atomic_write_record(path: Path, record: dict) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    source_hash, source_size = sha256_record(record)
    if source_size <= 0:
        raise ContractValidationError("raw artifact writer refuses empty content and silent fallback")

    if path.exists():
        existing_hash, existing_size = _sha256_path(path)
        if existing_size != source_size or existing_hash != source_hash:
            raise ContractValidationError("no_overwrite: existing artifact content differs")
        return existing_size, existing_hash

    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    digest = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(fd, "wb") as handle:
            for chunk in iter_raw_chunks(record):
                handle.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if size <= 0:
            raise ContractValidationError("raw artifact writer refuses empty content and silent fallback")
        if digest.hexdigest() != source_hash or size != source_size:
            raise ContractValidationError("atomic write verification failed")
        try:
            os.link(temp_path, path)
        except FileExistsError:
            existing_hash, existing_size = _sha256_path(path)
            if existing_size != source_size or existing_hash != source_hash:
                raise ContractValidationError("no_overwrite: concurrent artifact content differs")
        return size, source_hash
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["b3_raw_capture_inventory", "non_b3_raw_capture_inventory"]
    validate_inputs(inputs, required)

    records = (
        records_from_artifact(inputs[required[0]], "raw_file_inventory")
        + records_from_artifact(inputs[required[1]], "raw_file_inventory")
    )
    attempts = []
    for value in (inputs[required[0]], inputs[required[1]]):
        if isinstance(value, dict) and isinstance(value.get("attempts"), list):
            attempts.extend(dict(item) for item in value["attempts"] if isinstance(item, dict))
    artifact_root = Path(config["artifact_root"]) if config.get("artifact_root") else None
    output_records: list[dict] = []
    seen_artifacts: set[str] = set()

    for index, record in enumerate(records):
        source_id = record.get("source_id")
        if not source_id or not record.get("raw_preserved") or record.get("cleaning_applied"):
            raise ContractValidationError("raw artifact must preserve source bytes without cleaning")

        capture_id = derive_capture_id(record, index)
        raw_artifact_id = derive_raw_artifact_id(record, capture_id)
        if raw_artifact_id in seen_artifacts:
            raise ContractValidationError("raw_artifact_id must be unique")
        seen_artifacts.add(raw_artifact_id)

        source_path = raw_path_from_record(record)
        suffix_source = record.get("source_file_name") or (str(source_path) if source_path else "")
        suffix = Path(str(suffix_source)).suffix
        suffix = suffix or (f".{str(record.get('format')).lower()}" if record.get("format") else ".bin")
        dataset_id = record.get("dataset_id") or record.get("dataset") or "default"

        if artifact_root:
            path = artifact_root / f"{_safe(source_id)}-{_safe(dataset_id)}-{_safe(capture_id)}{suffix}"
            byte_count, content_hash = _atomic_write_record(path, record)
            path_exists = path.is_file()
            keep_inline_payload = False
        else:
            candidate = record.get("artifact_path") or record.get("raw_artifact_path") or record.get("source_file_path") or record.get("file_path")
            path = Path(str(candidate)) if candidate else Path("artifacts/raw") / _safe(source_id) / _safe(dataset_id) / _safe(capture_id) / f"payload{suffix}"
            path_exists = path.is_file()
            content_hash, byte_count = sha256_record(record)
            if byte_count <= 0:
                raise ContractValidationError("raw artifact writer refuses empty content and silent fallback")
            keep_inline_payload = not path_exists

        output = {
            "source_id": source_id,
            "source_name": record.get("source_name"),
            "source_name_inferred": record.get("source_name_inferred"),
            "source_type": record.get("source_type"),
            "source_category": record.get("source_category"),
            "dataset_id": record.get("dataset_id") or record.get("dataset"),
            "dataset": record.get("dataset"),
            "task_id": record.get("task_id"),
            "request_id": record.get("request_id"),
            "capture_id": capture_id,
            "partition_id": record.get("partition_id"),
            "page_id": record.get("page_id"),
            "artifact_id": raw_artifact_id,
            "raw_artifact_id": raw_artifact_id,
            "artifact_path": str(path),
            "raw_artifact_path": str(path),
            "path_exists": path_exists,
            "no_overwrite": True,
            "atomic_write": bool(artifact_root),
            "raw_preserved": True,
            "cleaning_applied": False,
            "byte_count": byte_count,
            "content_hash_during_write": content_hash,
            "available_at": record.get("available_at") or record.get("declared_available_at"),
            "declared_available_at": record.get("declared_available_at") or record.get("available_at"),
            "reference_time": record.get("reference_time") or record.get("source_reference_time") or record.get("source_reference_date"),
            "requested_at": record.get("requested_at"),
            "retrieved_at": record.get("retrieved_at"),
            "frequency": record.get("frequency"),
            "period_start": record.get("period_start"),
            "period_end": record.get("period_end"),
            "format": record.get("format"),
            "content_type": record.get("content_type"),
            "content_encoding": record.get("content_encoding"),
            "source_url": record.get("source_url"),
            "expected_sha256": record.get("expected_sha256"),
            "provider_etag": record.get("provider_etag") or record.get("etag"),
            "provider_last_modified": record.get("provider_last_modified") or record.get("last_modified"),
            "source_revision": record.get("source_revision"),
            "lineage_id": record.get("lineage_id"),
            "run_id": record.get("run_id") or record.get("ingestion_run_id"),
        }
        if keep_inline_payload:
            # Compatibility path for unit/local execution without configured storage.
            inline = record.get("raw_bytes")
            if isinstance(inline, bytearray):
                inline = bytes(inline)
            if isinstance(inline, bytes):
                output["raw_bytes"] = inline
            elif isinstance(record.get("raw_text"), str):
                output["raw_text"] = record["raw_text"]
            elif source_path is not None:
                output["source_file_path"] = str(source_path)
        output_records.append(output)

    digest = identity_digest(output_records)
    meta = {
        "artifact_id": f"raw-file-inventory-{digest[:12]}",
        "created_at": config.get("created_at", "2024-01-01T00:00:00Z"),
        "lineage_id": f"lineage-raw-file-inventory-{digest[:12]}",
        "pipeline_version": config.get("pipeline_version", "V14.1-RC4.1"),
        "records": output_records,
        "attempts": attempts,
    }
    store = {
        **meta,
        "artifact_id": f"raw-artifact-store-{digest[:12]}",
        "storage_backend": "local_filesystem" if artifact_root else "inline_or_existing_path",
        "artifact_root": str(artifact_root) if artifact_root else None,
    }
    return {
        "module_id": "P1.S3.M01",
        "module_name": "raw_artifact_writer",
        "phase": "phase_01_ingestion",
        "subphase": "P1.S3",
        "contract": "P1_S3_M01_raw_artifact_writer.yaml",
        "required_inputs": required,
        "outputs": {"raw_file_inventory": meta, "raw_artifact_store": store},
    }
