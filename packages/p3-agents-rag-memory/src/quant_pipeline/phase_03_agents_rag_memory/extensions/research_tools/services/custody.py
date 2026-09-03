"""P3.S33.M02 P1 custody index constrained by P2 lineage."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..contracts.artifacts import ArtifactStatus
from ..contracts.boundary_artifacts import (
    CustodyQualificationRecord,
    CustodyStatus,
    Phase1CustodyQualificationReport,
    Phase1RawEvidenceReferenceIndex,
    Phase2ResearchViewManifest,
    RawEvidenceReference,
)
from ..core.hashing import content_hash
from .artifact_construction import finalize, lineage
from .input_contracts import as_mapping, as_records, first_value, parse_datetime, safe_storage_token


def _record_map(value: object, id_keys: tuple[str, ...]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for record in as_records(value):
        raw_id = first_value(record, id_keys)
        if raw_id in (None, ""):
            continue
        key = str(raw_id)
        if key in result:
            raise ValueError(f"duplicate record identifier: {key}")
        result[key] = record
    return result


def _string(record: Mapping[str, Any], keys: tuple[str, ...], fallback: str) -> str:
    value = first_value(record, keys)
    return fallback if value in (None, "") else str(value)


def _int(record: Mapping[str, Any], keys: tuple[str, ...], fallback: int = 0) -> int:
    value = first_value(record, keys)
    if value in (None, ""):
        return fallback
    return max(0, int(value))


def _hash_or_derived(value: Any, payload: object) -> str:
    text = "" if value in (None, "") else str(value).lower()
    if len(text) == 64 and all(char in "0123456789abcdef" for char in text):
        return text
    return content_hash(payload)


def build_phase1_custody_index(
    *,
    inputs: dict[str, Any],
    view_manifest: Phase2ResearchViewManifest,
    contract_version: str = "1.0.0",
) -> tuple[Phase1RawEvidenceReferenceIndex, Phase1CustodyQualificationReport]:
    snapshots = _record_map(inputs.get("source_snapshot_registry", {}), ("raw_artifact_id", "artifact_id"))
    inventory = _record_map(inputs.get("raw_file_inventory", {}), ("raw_artifact_id", "artifact_id"))
    readability = _record_map(inputs.get("raw_readability_report", {}), ("raw_artifact_id", "artifact_id"))
    schema_hints = _record_map(inputs.get("raw_schema_hint_report", {}), ("raw_artifact_id", "artifact_id"))
    errors = _record_map(inputs.get("ingestion_error_report", {}), ("raw_artifact_id", "artifact_id"))

    p2_by_source: dict[str, set[str]] = {}
    p2_lineage_by_source: dict[str, set[str]] = {}
    for view in view_manifest.views:
        for source_id in view.source_ids:
            p2_by_source.setdefault(source_id, set()).add(view.artifact_id)
            p2_lineage_by_source.setdefault(source_id, set()).update(view.lineage_ids)

    records: list[RawEvidenceReference] = []
    qualification: list[CustodyQualificationRecord] = []
    for raw_id, snapshot in sorted(snapshots.items()):
        inv = inventory.get(raw_id, {})
        read = readability.get(raw_id, {})
        hint = schema_hints.get(raw_id, {})
        source_id = _string(snapshot, ("source_id", "provider_id"), "unknown_source")
        snapshot_id = _string(snapshot, ("snapshot_id", "ingestion_run_id", "run_id"), "unknown_snapshot")
        snapshot_hash = _hash_or_derived(first_value(snapshot, ("file_hash", "sha256", "content_hash")), snapshot)
        inventory_hash_raw = first_value(inv, ("file_hash", "sha256", "content_hash"))
        inventory_hash = None if inventory_hash_raw in (None, "") else _hash_or_derived(inventory_hash_raw, inv)
        readable = _string(
            read or snapshot,
            ("readability_status", "status", "readable"),
            "UNKNOWN",
        ).upper()
        linked_artifacts = tuple(sorted(p2_by_source.get(source_id, set())))
        linked_lineage = tuple(sorted(p2_lineage_by_source.get(source_id, set())))
        reason_codes: list[str] = []
        status = CustodyStatus.AUTHORIZED
        if inventory_hash is not None and inventory_hash != snapshot_hash:
            status = CustodyStatus.HASH_MISMATCH
            reason_codes.append("P3RT-PIT-P1-HASH-MISMATCH")
        elif readable not in {"READABLE", "PASS", "OK", "TRUE", "VALID"}:
            status = CustodyStatus.UNREADABLE
            reason_codes.append("P3RT-DATA-P1-UNREADABLE")
        elif not linked_artifacts:
            status = CustodyStatus.UNAUTHORIZED_ORPHAN
            reason_codes.append("P3RT-AUTH-P1-ORPHAN")
        elif raw_id in errors:
            status = CustodyStatus.DEGRADED
            reason_codes.append("P3RT-DATA-P1-INGESTION-ERROR")

        storage_ref = first_value(snapshot, ("raw_artifact_path", "storage_ref", "path", "uri"))
        token = safe_storage_token(storage_ref, raw_artifact_id=raw_id, snapshot_id=snapshot_id)
        schema_fingerprint_raw = first_value(hint, ("schema_fingerprint", "content_hash", "sha256"))
        schema_fingerprint = (
            None if schema_fingerprint_raw in (None, "") else _hash_or_derived(schema_fingerprint_raw, hint)
        )
        record = RawEvidenceReference(
            raw_artifact_id=raw_id,
            source_id=source_id,
            snapshot_id=snapshot_id,
            file_hash=snapshot_hash,
            file_size_bytes=_int(snapshot or inv, ("file_size_bytes", "file_size", "size_bytes"), 0),
            media_type=_string(snapshot or inv, ("media_type", "content_type", "mime_type"), "application/octet-stream"),
            readability_status=readable,
            schema_fingerprint=schema_fingerprint,
            storage_ref_token=token,
            captured_at=parse_datetime(first_value(snapshot, ("captured_at", "ingested_at", "created_at"))),
            declared_available_at=parse_datetime(first_value(snapshot, ("declared_available_at", "available_at"))),
            linked_p2_artifact_ids=linked_artifacts,
            linked_p2_lineage_ids=linked_lineage,
            custody_status=status,
            reason_codes=tuple(reason_codes),
        )
        records.append(record)
        checks = ["snapshot_hash_present", "storage_reference_redacted", "p2_link_checked"]
        if inventory_hash is not None:
            checks.append("inventory_hash_compared")
        qualification.append(CustodyQualificationRecord(
            raw_artifact_id=raw_id,
            status=status,
            checks=tuple(checks),
            reason_codes=tuple(reason_codes),
        ))

    artifact_status = ArtifactStatus.READY
    if any(record.custody_status != CustodyStatus.AUTHORIZED for record in records):
        artifact_status = ArtifactStatus.DEGRADED
    source_inputs = [
        inputs.get("handoff_manifest_to_phase_2"),
        inputs.get("source_registry"),
        inputs.get("raw_file_inventory"),
        inputs.get("source_snapshot_registry"),
        inputs.get("raw_readability_report"),
        inputs.get("raw_schema_hint_report"),
        inputs.get("ingestion_error_report"),
        view_manifest,
    ]
    index = finalize(Phase1RawEvidenceReferenceIndex, {
        "status": artifact_status,
        "lineage": lineage("P3.S33.M02", contract_version, source_inputs),
        "reason_codes": () if artifact_status == ArtifactStatus.READY else ("P3RT-QUALITY-P1-CUSTODY-PARTIAL",),
        "records": tuple(records),
        "record_count": len(records),
    })
    report = finalize(Phase1CustodyQualificationReport, {
        "status": artifact_status,
        "lineage": lineage("P3.S33.M02", contract_version, [index, inputs.get("quality_report_phase_2")]),
        "reason_codes": index.reason_codes,
        "records": tuple(qualification),
        "authorized_count": sum(item.status == CustodyStatus.AUTHORIZED for item in qualification),
        "blocked_count": sum(item.status != CustodyStatus.AUTHORIZED for item in qualification),
    })
    return index, report
