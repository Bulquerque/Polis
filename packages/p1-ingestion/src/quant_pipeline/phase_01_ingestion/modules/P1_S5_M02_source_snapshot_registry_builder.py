from __future__ import annotations

from ._module_executor import ContractValidationError, _stable_digest
from ..core import identity_digest
from ._p1_semantic_helpers import records_from_artifact, validate_inputs
from ._s345_semantics import derive_snapshot_id, resolve_run_id, source_registry_map


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["source_registry", "ingestion_manifest", "versioned_raw_file_inventory"]
    validate_inputs(inputs, required)

    files = records_from_artifact(inputs["versioned_raw_file_inventory"], "versioned_raw_file_inventory")
    manifest = inputs["ingestion_manifest"] if isinstance(inputs["ingestion_manifest"], dict) else {}
    task_results = {
        str(item.get("task_id")): item
        for item in manifest.get("task_results", [])
        if isinstance(item, dict) and item.get("task_id")
    }
    source_map = source_registry_map(inputs["source_registry"])
    run_id = resolve_run_id(config, manifest=manifest, records=files)

    snapshots: list[dict] = []
    seen_snapshot_ids: set[str] = set()
    for record in files:
        source_id = record.get("source_id")
        file_hash = record.get("file_hash")
        if not source_id or not file_hash:
            raise ContractValidationError("snapshot must reference source and hash")
        source_meta = source_map.get(str(source_id), {})
        task_result = task_results.get(str(record.get("task_id")), {})

        snapshot_base = {
            "ingestion_run_id": run_id,
            "source_id": source_id,
            "source_name": record.get("source_name") or source_meta.get("source_name") or source_meta.get("name"),
            "source_type": record.get("source_type") or source_meta.get("source_type"),
            "source_category": record.get("source_category") or source_meta.get("source_category"),
            "dataset_id": record.get("dataset_id") or record.get("dataset"),
            "dataset": record.get("dataset"),
            "asset": record.get("asset"),
            "frequency": record.get("frequency"),
            "period_start": record.get("period_start"),
            "period_end": record.get("period_end"),
            "format": record.get("format"),
            "source_url": record.get("source_url"),
            "task_id": record.get("task_id"),
            "request_id": record.get("request_id"),
            "capture_id": record.get("capture_id"),
            "partition_id": record.get("partition_id"),
            "page_id": record.get("page_id"),
            "raw_artifact_id": record.get("raw_artifact_id") or record.get("artifact_id"),
            "raw_artifact_path": record.get("raw_artifact_path") or record.get("artifact_path"),
            "file_hash": file_hash,
            "file_size_bytes": record.get("file_size_bytes"),
            "ingested_at": record.get("retrieved_at") or config.get("created_at"),
            "reference_time": (record.get("reference_time") or record.get("source_reference_time") or record.get("source_reference_date") or record.get("period_end") or record.get("period_start")),
            "source_reference_basis": (
                "explicit_reference_time" if (record.get("reference_time") or record.get("source_reference_time") or record.get("source_reference_date"))
                else "period_end" if record.get("period_end")
                else "period_start" if record.get("period_start")
                else "unknown"
            ),
            "declared_available_at": record.get("declared_available_at") or record.get("available_at"),
            "requested_at": record.get("requested_at"),
            "retrieved_at": record.get("retrieved_at"),
            "readability_status": task_result.get("readability_status"),
            "schema_fingerprint": task_result.get("schema_fingerprint"),
            "task_state": task_result.get("final_state"),
            "is_blocking": bool(task_result.get("is_blocking")),
            "lineage_id": record.get("lineage_id"),
            "pipeline_version": config.get("pipeline_version", "V14.1-RC4.1"),
        }
        snapshot_id = derive_snapshot_id({**record, **snapshot_base}, run_id)
        if snapshot_id in seen_snapshot_ids:
            raise ContractValidationError("source_snapshot_unique violation: snapshot_id must be unique")
        seen_snapshot_ids.add(snapshot_id)
        snapshots.append({"snapshot_id": snapshot_id, **snapshot_base})

    digest = identity_digest(snapshots)
    return {
        "module_id": "P1.S5.M02",
        "module_name": "source_snapshot_registry_builder",
        "phase": "phase_01_ingestion",
        "subphase": "P1.S5",
        "contract": "P1_S5_M02_source_snapshot_registry_builder.yaml",
        "required_inputs": required,
        "outputs": {
            "source_snapshot_registry": {
                "artifact_id": f"source-snapshot-registry-{digest[:12]}",
                "created_at": config.get("created_at", "2024-01-01T00:00:00Z"),
                "lineage_id": f"lineage-source-snapshot-registry-{digest[:12]}",
                "pipeline_version": config.get("pipeline_version", "V14.1-RC4.1"),
                "ingestion_run_id": run_id,
                "snapshots": snapshots,
            }
        },
    }
