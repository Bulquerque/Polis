from __future__ import annotations

from ._module_executor import ContractValidationError, _stable_digest
from ..core import identity_digest
from ._p1_semantic_helpers import records_from_artifact, validate_inputs
from ._s345_semantics import sha256_record, stable_id


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["raw_file_inventory", "raw_artifact_store"]
    validate_inputs(inputs, required)
    records = records_from_artifact(inputs["raw_file_inventory"], "raw_file_inventory")
    attempts = []
    if isinstance(inputs.get("raw_file_inventory"), dict) and isinstance(inputs["raw_file_inventory"].get("attempts"), list):
        attempts = [dict(item) for item in inputs["raw_file_inventory"]["attempts"] if isinstance(item, dict)]

    versioned: list[dict] = []
    seen: set[str] = set()
    for record in records:
        artifact_id = record.get("raw_artifact_id") or record.get("artifact_id")
        if not artifact_id or artifact_id in seen:
            raise ContractValidationError("artifact_id must be unique and present")
        seen.add(str(artifact_id))

        file_hash, file_size = sha256_record(record)
        if file_size <= 0:
            raise ContractValidationError("file size must be positive")
        expected_hash = record.get("expected_sha256")
        if expected_hash and str(expected_hash).lower() != file_hash.lower():
            raise ContractValidationError("stored artifact hash does not match frozen provenance")
        write_hash = record.get("content_hash_during_write")
        if write_hash and str(write_hash).lower() != file_hash.lower():
            raise ContractValidationError("post-write hash verification failed")

        version_id = stable_id(
            "raw-version",
            {
                "artifact_id": artifact_id,
                "capture_id": record.get("capture_id"),
                "file_hash": file_hash,
                "provider_etag": record.get("provider_etag"),
                "source_revision": record.get("source_revision"),
            },
        )
        versioned.append(
            {
                **record,
                "artifact_id": artifact_id,
                "raw_artifact_id": artifact_id,
                "file_hash": file_hash,
                "content_hash": file_hash,
                "file_size_bytes": file_size,
                "hash_algorithm": "sha256",
                "hash_verified": True,
                "expected_hash_match": True if expected_hash else None,
                "version_id": version_id,
            }
        )

    digest = identity_digest(versioned)
    return {
        "module_id": "P1.S3.M02",
        "module_name": "hash_version_manager",
        "phase": "phase_01_ingestion",
        "subphase": "P1.S3",
        "contract": "P1_S3_M02_hash_version_manager.yaml",
        "required_inputs": required,
        "outputs": {
            "versioned_raw_file_inventory": {
                "artifact_id": f"versioned-raw-{digest[:12]}",
                "created_at": config.get("created_at", "2024-01-01T00:00:00Z"),
                "lineage_id": f"lineage-versioned-raw-{digest[:12]}",
                "pipeline_version": config.get("pipeline_version", "V14.1-RC4.1"),
                "records": versioned,
                "attempts": attempts,
            }
        },
    }
