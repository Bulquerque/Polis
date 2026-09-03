from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import zipfile

from ._module_executor import _stable_digest
from ._p1_semantic_helpers import records_from_artifact, validate_inputs
from ._s345_semantics import (
    find_related_record,
    json_structure_from_object,
    raw_path_from_record,
    raw_prefix,
)


def _declared_format(record: dict) -> str:
    declared = str(record.get("format") or "").strip().lower()
    if declared:
        return declared
    path = raw_path_from_record(record)
    suffix = (path.suffix if path else Path(str(record.get("artifact_path") or record.get("raw_artifact_path") or "")).suffix)
    return suffix.lstrip(".").lower() or "binary"


def _inline_bytes(record: dict) -> bytes | None:
    raw = record.get("raw_bytes")
    if isinstance(raw, bytearray):
        return bytes(raw)
    if isinstance(raw, bytes):
        return raw
    text = record.get("raw_text")
    if isinstance(text, str):
        return text.encode("utf-8")
    return None


def _structural_hint(record: dict, readability: dict | None) -> dict:
    fmt = _declared_format(record)
    base = {
        "artifact_id": record.get("artifact_id"),
        "raw_artifact_id": record.get("raw_artifact_id") or record.get("artifact_id"),
        "capture_id": record.get("capture_id"),
        "task_id": record.get("task_id"),
        "source_id": record.get("source_id"),
        "schema_hint": fmt,
        "format": fmt,
        "is_clean_schema": False,
    }
    if readability and readability.get("readability_status") != "readable":
        return {
            **base,
            "hint_status": "not_applicable",
            "reason": readability.get("issue") or "upstream_unreadable",
            "schema_fingerprint": None,
        }

    path = raw_path_from_record(record)
    inline = None if path is not None else _inline_bytes(record)
    if path is None and inline is None:
        return {**base, "hint_status": "not_applicable", "reason": "artifact_missing", "schema_fingerprint": None}

    details: dict = {}
    try:
        if fmt == "json":
            if path is not None:
                with path.open("r", encoding="utf-8") as handle:
                    obj = json.load(handle)
            else:
                obj = json.loads(inline.decode("utf-8"))
            keys, record_count = json_structure_from_object(obj)
            details["top_level_keys"] = keys
            details["record_count_estimate"] = record_count
        elif fmt == "csv":
            sample_bytes = raw_prefix(record, 8192)
            try:
                text = sample_bytes.decode("utf-8-sig")
                encoding = "utf-8-sig"
            except UnicodeDecodeError:
                text = sample_bytes.decode("latin-1")
                encoding = "latin-1"
            details["encoding_hint"] = encoding
            try:
                dialect = csv.Sniffer().sniff(text, delimiters=",;\t|")
                delimiter = dialect.delimiter
            except csv.Error:
                delimiter = ","
            details["delimiter_hint"] = delimiter
            reader = csv.reader(io.StringIO(text), delimiter=delimiter)
            header = next(reader, [])
            details["raw_columns"] = header or None
        elif fmt == "zip":
            source = path if path is not None else io.BytesIO(inline)
            with zipfile.ZipFile(source) as archive:
                names = archive.namelist()
                details["container_members"] = names[:100]
                details["member_count"] = len(names)
    except Exception as exc:
        return {**base, "hint_status": "partial", "reason": type(exc).__name__, "schema_fingerprint": None}

    fingerprint_payload = {"format": fmt, **details}
    return {
        **base,
        "hint_status": "available",
        **details,
        "schema_fingerprint": _stable_digest(fingerprint_payload),
    }


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["versioned_raw_file_inventory", "raw_readability_report"]
    validate_inputs(inputs, required)
    records = records_from_artifact(inputs[required[0]], "versioned_raw_file_inventory")
    checks = inputs["raw_readability_report"].get("checks", []) if isinstance(inputs["raw_readability_report"], dict) else []

    hints = [_structural_hint(record, find_related_record(checks, record)) for record in records]
    digest = _stable_digest(hints)
    return {
        "module_id": "P1.S4.M02",
        "module_name": "raw_schema_hint_detector",
        "phase": "phase_01_ingestion",
        "subphase": "P1.S4",
        "contract": "P1_S4_M02_raw_schema_hint_detector.yaml",
        "required_inputs": required,
        "outputs": {
            "raw_schema_hint_report": {
                "artifact_id": f"schema-hint-{digest[:12]}",
                "created_at": config.get("created_at", "2024-01-01T00:00:00Z"),
                "lineage_id": f"lineage-schema-hint-{digest[:12]}",
                "pipeline_version": config.get("pipeline_version", "V14.1-RC4.1"),
                "hints": hints,
                "cleaning_applied": False,
            }
        },
    }
