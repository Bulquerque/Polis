from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ._module_executor import ContractValidationError, _stable_digest
from ..core import deterministic_id, identity_digest
from ._p1_semantic_helpers import records_from_artifact, validate_inputs
from ._s345_semantics import find_related_record, source_registry_map, stable_id


def _records(value: dict, field: str) -> list[dict]:
    if isinstance(value, dict) and isinstance(value.get(field), list):
        return value[field]
    return []


def _bea_observations(record: dict) -> list[dict]:
    """Materialize BEA Results.Data while retaining capture custody."""
    provider = str(record.get("source_id") or "").lower()
    if provider not in {"bea", "eia"}:
        return []
    path = Path(str(record.get("raw_artifact_path") or ""))
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if provider == "bea":
            rows = payload["BEAAPI"]["Results"].get("Data", [])
        else:
            rows = (payload.get("response") or {}).get("data", [])
    except (OSError, ValueError, KeyError, TypeError):
        return []
    capture_id = str(record.get("capture_id") or record.get("handoff_artifact_id"))
    raw_hash = str(record.get("file_hash") or hashlib.sha256(path.read_bytes()).hexdigest())
    observations = []
    for source_row_number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        key = (row.get("TableName") or row.get("respondent"), row.get("LineNumber") or row.get("period"), row.get("TimePeriod") or row.get("period"))
        raw_value = row.get("DataValue") if provider == "bea" else row.get("value")
        try:
            numeric = float(str(raw_value).replace(",", "")) if raw_value not in (None, "") else None
        except (TypeError, ValueError):
            numeric = None
        observations.append({
            "capture_id": capture_id,
            "request_id": record.get("request_id"),
            "raw_record_id": deterministic_id(f"{provider}-raw-record", capture_id, source_row_number, key),
            "source_row_number": source_row_number,
            "provider": provider.upper(),
            "dataset_name": "NIPA" if provider == "bea" else "EIA_RTO_REGION_DATA",
            "table_name": row.get("TableName") if provider == "bea" else None,
            "line_number": row.get("LineNumber") if provider == "bea" else None,
            "line_description": row.get("LineDescription") if provider == "bea" else row.get("type-name"),
            "time_period": row.get("TimePeriod") if provider == "bea" else row.get("period"),
            "data_value_raw": raw_value,
            "data_value_numeric": numeric,
            "unit": row.get("CL_UNIT") if provider == "bea" else row.get("value-units"),
            "unit_multiplier": row.get("UNIT_MULT") if provider == "bea" else None,
            "note_ref": row.get("NoteRef") if provider == "bea" else None,
            "captured_at": record.get("retrieved_at") or record.get("ingested_at"),
            "sanitized_raw_hash": raw_hash,
        })
    return observations


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    # raw_file_inventory is part of the frozen contract. For compatibility with
    # older direct callers, fall back to the versioned inventory only when the
    # unversioned inventory was not supplied.
    normalized_inputs = dict(inputs)
    if "raw_file_inventory" not in normalized_inputs and "versioned_raw_file_inventory" in normalized_inputs:
        normalized_inputs["raw_file_inventory"] = normalized_inputs["versioned_raw_file_inventory"]

    required = [
        "ingestion_manifest",
        "source_registry",
        "source_snapshot_registry",
        "raw_file_inventory",
        "versioned_raw_file_inventory",
        "raw_readability_report",
        "raw_schema_hint_report",
        "ingestion_error_report",
    ]
    validate_inputs(normalized_inputs, required)

    errors = records_from_artifact(normalized_inputs["ingestion_error_report"], "ingestion_error_report")
    blocking_errors = [error for error in errors if isinstance(error, dict) and error.get("is_blocking")]
    if blocking_errors:
        raise ContractValidationError("no_blocking_error_open violation")

    snapshots = records_from_artifact(normalized_inputs["source_snapshot_registry"], "source_snapshot_registry")
    readability_checks = _records(normalized_inputs["raw_readability_report"], "checks")
    hints = _records(normalized_inputs["raw_schema_hint_report"], "hints")
    source_map = source_registry_map(normalized_inputs["source_registry"])

    handoff: list[dict] = []
    seen_ids: set[str] = set()
    for snapshot in snapshots:
        if snapshot.get("is_blocking"):
            raise ContractValidationError("no_blocking_error_open violation")
        if not snapshot.get("file_hash"):
            raise ContractValidationError("hashes_present violation")
        if not snapshot.get("raw_artifact_id"):
            raise ContractValidationError("raw_artifact_id must be present")

        source_id = snapshot.get("source_id")
        source_meta = source_map.get(str(source_id), {})
        readability = find_related_record(readability_checks, snapshot)
        hint = find_related_record(hints, snapshot)
        error = find_related_record(errors, snapshot)

        handoff_id = stable_id(
            "handoff",
            {
                "snapshot_id": snapshot.get("snapshot_id"),
                "capture_id": snapshot.get("capture_id"),
                "raw_artifact_id": snapshot.get("raw_artifact_id"),
                "file_hash": snapshot.get("file_hash"),
            },
        )
        if handoff_id in seen_ids:
            raise ContractValidationError("handoff_artifact_id must be unique")
        seen_ids.add(handoff_id)

        file_size = snapshot.get("file_size_bytes")
        if file_size is None or int(file_size) <= 0:
            raise ContractValidationError("file_size_bytes must be positive")

        record = {
            "handoff_artifact_id": handoff_id,
            "snapshot_id": snapshot.get("snapshot_id"),
            "ingestion_run_id": snapshot.get("ingestion_run_id"),
            "source_id": source_id,
            "source_name": snapshot.get("source_name") or source_meta.get("source_name") or source_meta.get("name") or str(source_id),
            "source_name_inferred": bool(
                snapshot.get("source_name_inferred")
                or source_meta.get("source_name_inferred")
                or not (snapshot.get("source_name") or source_meta.get("source_name") or source_meta.get("name"))
            ),
            "source_type": snapshot.get("source_type") or source_meta.get("source_type"),
            "source_category": snapshot.get("source_category") or source_meta.get("source_category"),
            "dataset_id": snapshot.get("dataset_id") or snapshot.get("dataset"),
            "dataset": snapshot.get("dataset"),
            "asset": snapshot.get("asset"),
            "frequency": snapshot.get("frequency"),
            "period_start": snapshot.get("period_start"),
            "period_end": snapshot.get("period_end"),
            "format": snapshot.get("format"),
            "source_url": snapshot.get("source_url"),
            "task_id": snapshot.get("task_id"),
            "request_id": snapshot.get("request_id"),
            "capture_id": snapshot.get("capture_id"),
            "partition_id": snapshot.get("partition_id"),
            "page_id": snapshot.get("page_id"),
            "raw_artifact_id": snapshot.get("raw_artifact_id"),
            "raw_artifact_path": snapshot.get("raw_artifact_path"),
            "file_hash": snapshot.get("file_hash"),
            "file_size_bytes": file_size,
            "ingested_at": snapshot.get("ingested_at"),
            "source_reference_time": snapshot.get("reference_time"),
            # Legacy alias retained, but its provenance is explicit and it is never
            # populated from availability timestamps.
            "source_reference_date": snapshot.get("reference_time"),
            "source_reference_basis": snapshot.get("source_reference_basis") or ("explicit_reference_time" if snapshot.get("reference_time") else "unknown"),
            "declared_available_at": snapshot.get("declared_available_at"),
            "requested_at": snapshot.get("requested_at"),
            "retrieved_at": snapshot.get("retrieved_at"),
            "readability_status": (
                readability.get("readability_status") if readability else snapshot.get("readability_status")
            ),
            "schema_hint_id": (
                deterministic_id("schema-hint", snapshot.get("raw_artifact_id"), hint.get("schema_fingerprint"))
                if hint and hint.get("schema_fingerprint") else None
            ),
            "schema_fingerprint": hint.get("schema_fingerprint") if hint else snapshot.get("schema_fingerprint"),
            "error_flag": bool(error.get("error_flag")) if error else False,
            "warning_flag": bool(error and error.get("error_flag") and not error.get("is_blocking")),
            "error_code": error.get("error_code") if error else None,
            "lineage_id": snapshot.get("lineage_id"),
            "pipeline_version": snapshot.get("pipeline_version") or config.get("pipeline_version", "V14.1-RC4.1"),
        }
        record["economic_observations"] = _bea_observations(record)
        handoff.append(record)

    if not bool(config.get("allow_partial_success", False)):
        blocking_errors = [
            item for item in errors
            if isinstance(item, dict)
            and item.get("error_flag")
            and (item.get("is_blocking") or config.get("allow_partial_success_explicit"))
        ]
        if blocking_errors:
            raise ContractValidationError(
                "allow_partial_success=false blocks handoff while ingestion errors remain open"
            )

    digest = identity_digest(handoff)
    manifest = {
        "artifact_id": f"handoff-manifest-{digest[:12]}",
        "created_at": config.get("created_at", "2024-01-01T00:00:00Z"),
        "lineage_id": f"lineage-handoff-manifest-{digest[:12]}",
        "pipeline_version": config.get("pipeline_version", "V14.1-RC4.1"),
        "records": handoff,
        "no_blocking_error_open": True,
        "record_count": len(handoff),
    }
    return {
        "module_id": "P1.S5.M04",
        "module_name": "phase2_handoff_packager",
        "phase": "phase_01_ingestion",
        "subphase": "P1.S5",
        "contract": "P1_S5_M04_phase2_handoff_packager.yaml",
        "required_inputs": required,
        "outputs": {
            "handoff_manifest_to_phase_2": manifest,
            "source_registry": normalized_inputs["source_registry"],
            "raw_file_inventory": normalized_inputs["raw_file_inventory"],
            "source_snapshot_registry": normalized_inputs["source_snapshot_registry"],
            "raw_readability_report": normalized_inputs["raw_readability_report"],
            "raw_schema_hint_report": normalized_inputs["raw_schema_hint_report"],
            "ingestion_error_report": normalized_inputs["ingestion_error_report"],
        },
    }
