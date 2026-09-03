from __future__ import annotations

import csv
import gzip
import io
import json
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

from ._module_executor import _stable_digest
from ..core import identity_digest
from ._p1_semantic_helpers import records_from_artifact, validate_inputs
from ._s345_semantics import raw_path_from_record, raw_prefix, raw_size


def _declared_format(record: dict) -> str:
    value = str(record.get("format") or "").strip().lower()
    if value:
        return value
    path = raw_path_from_record(record)
    suffix = (path.suffix if path else Path(str(record.get("artifact_path") or record.get("raw_artifact_path") or "")).suffix)
    return suffix.lower().lstrip(".") or "binary"


def _load_inline(record: dict) -> bytes | None:
    raw = record.get("raw_bytes")
    if isinstance(raw, bytearray):
        return bytes(raw)
    if isinstance(raw, bytes):
        return raw
    text = record.get("raw_text")
    if isinstance(text, str):
        return text.encode("utf-8")
    return None


def _check_payload(record: dict, config: dict) -> tuple[list[str], dict]:
    issues: list[str] = []
    diagnostics: dict = {}
    path = raw_path_from_record(record)
    inline = None if path is not None else _load_inline(record)
    if path is None and inline is None:
        return ["artifact_missing"], diagnostics

    try:
        size = raw_size(record)
    except Exception:
        return ["artifact_missing"], diagnostics
    diagnostics["observed_size_bytes"] = size
    if size <= 0:
        return ["empty_file"], diagnostics

    declared_length = record.get("content_length") or record.get("byte_count")
    if declared_length is not None:
        try:
            if int(declared_length) != size:
                issues.append("content_length_mismatch")
        except (TypeError, ValueError):
            issues.append("invalid_content_length_metadata")

    fmt = _declared_format(record)
    prefix = raw_prefix(record, 8192)
    lower = prefix.lstrip()[:128].lower()

    if fmt in {"csv", "txt"} and lower.startswith((b"<!doctype html", b"<html")):
        issues.append("html_saved_as_csv")
    elif fmt == "json":
        try:
            if path is not None:
                with path.open("r", encoding="utf-8") as handle:
                    json.load(handle)
            else:
                json.loads(inline.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, OSError):
            issues.append("invalid_json")
    elif fmt in {"xml", "atom"}:
        try:
            if path is not None:
                ET.parse(path)
            else:
                ET.fromstring(inline)
        except (ET.ParseError, OSError):
            issues.append("invalid_xml")
    elif fmt == "zip":
        try:
            source = path if path is not None else io.BytesIO(inline)
            with zipfile.ZipFile(source) as archive:
                infos = archive.infolist()
                diagnostics["zip_member_count"] = len(infos)
                max_members = int(config.get("max_archive_members", 10000))
                max_uncompressed = int(config.get("max_archive_uncompressed_bytes", 2 * 1024 * 1024 * 1024))
                max_ratio = float(config.get("max_archive_compression_ratio", 1000.0))
                total_uncompressed = sum(max(0, info.file_size) for info in infos)
                diagnostics["zip_uncompressed_bytes"] = total_uncompressed
                if len(infos) > max_members or total_uncompressed > max_uncompressed:
                    issues.append("archive_safety_limit_exceeded")
                for info in infos:
                    compressed = max(1, info.compress_size)
                    if info.file_size / compressed > max_ratio:
                        issues.append("archive_safety_limit_exceeded")
                        break
                if "archive_safety_limit_exceeded" not in issues:
                    bad_member = archive.testzip()
                    if bad_member:
                        issues.append("archive_corruption")
        except (zipfile.BadZipFile, OSError):
            issues.append("archive_corruption")
    elif fmt in {"gz", "gzip"}:
        try:
            source = path.open("rb") if path is not None else io.BytesIO(inline)
            max_uncompressed = int(config.get("max_archive_uncompressed_bytes", 2 * 1024 * 1024 * 1024))
            expanded = 0
            try:
                with gzip.GzipFile(fileobj=source) as handle:
                    while True:
                        chunk = handle.read(1024 * 1024)
                        if not chunk:
                            break
                        expanded += len(chunk)
                        if expanded > max_uncompressed:
                            issues.append("archive_safety_limit_exceeded")
                            break
                diagnostics["gzip_uncompressed_bytes"] = expanded
            finally:
                source.close()
        except (OSError, EOFError):
            issues.append("gzip_corruption")
    elif fmt == "parquet":
        try:
            if size < 8:
                issues.append("invalid_parquet_container")
            elif path is not None:
                with path.open("rb") as handle:
                    start = handle.read(4)
                    handle.seek(-4, 2)
                    end = handle.read(4)
                if start != b"PAR1" or end != b"PAR1":
                    issues.append("invalid_parquet_container")
            elif not (inline.startswith(b"PAR1") and inline.endswith(b"PAR1")):
                issues.append("invalid_parquet_container")
        except OSError:
            issues.append("invalid_parquet_container")

    if fmt == "csv" and "html_saved_as_csv" not in issues:
        sample_bytes = prefix
        try:
            text = sample_bytes.decode("utf-8-sig")
            diagnostics["encoding_hint"] = "utf-8-sig"
        except UnicodeDecodeError:
            text = sample_bytes.decode("latin-1")
            diagnostics["encoding_hint"] = "latin-1"
        try:
            dialect = csv.Sniffer().sniff(text, delimiters=",;\t|")
            diagnostics["delimiter_hint"] = dialect.delimiter
        except csv.Error:
            diagnostics["delimiter_hint"] = None

    return sorted(set(issues)), diagnostics


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["versioned_raw_file_inventory"]
    validate_inputs(inputs, required)
    records = records_from_artifact(inputs[required[0]], "versioned_raw_file_inventory")

    checks: list[dict] = []
    for record in records:
        issues, diagnostics = _check_payload(record, config)
        status = "readable" if not issues else "unreadable"
        checks.append(
            {
                "artifact_id": record.get("artifact_id"),
                "raw_artifact_id": record.get("raw_artifact_id") or record.get("artifact_id"),
                "capture_id": record.get("capture_id"),
                "task_id": record.get("task_id"),
                "source_id": record.get("source_id"),
                "readability_status": status,
                "empty_file_flagged": "empty_file" in issues,
                "issue": issues[0] if issues else None,
                "issue_codes": issues,
                "is_blocking": bool(issues),
                "checks": {
                    "artifact_exists": "artifact_missing" not in issues,
                    "non_empty": "empty_file" not in issues,
                    "container_integrity": not any(i in issues for i in {"archive_corruption", "gzip_corruption", "invalid_parquet_container", "archive_safety_limit_exceeded"}),
                    "syntax_valid": not any(i in issues for i in {"invalid_json", "invalid_xml", "html_saved_as_csv"}),
                },
                **diagnostics,
            }
        )

    digest = identity_digest(checks)
    return {
        "module_id": "P1.S4.M01",
        "module_name": "raw_readability_checker",
        "phase": "phase_01_ingestion",
        "subphase": "P1.S4",
        "contract": "P1_S4_M01_raw_readability_checker.yaml",
        "required_inputs": required,
        "outputs": {
            "raw_readability_report": {
                "artifact_id": f"readability-{digest[:12]}",
                "created_at": config.get("created_at", "2024-01-01T00:00:00Z"),
                "lineage_id": f"lineage-readability-{digest[:12]}",
                "pipeline_version": config.get("pipeline_version", "V14.1-RC4.1"),
                "checks": checks,
            }
        },
    }
