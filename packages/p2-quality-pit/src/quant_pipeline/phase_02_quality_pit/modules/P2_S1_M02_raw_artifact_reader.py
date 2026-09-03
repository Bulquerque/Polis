from __future__ import annotations

from ._module_executor import ContractValidationError
from ._p2_semantic_helpers import artifact, no_forbidden_rows, records, require_inputs
from ._s1_core import (
    compute_sha256,
    detect_format,
    enrich_with_provenance,
    is_sha256,
    read_artifact_rows,
    resolve_artifact_path,
)

_REQUIRED_INPUTS = ["validated_phase1_handoff_bundle"]
_ALLOWED_READABILITY = {"readable", "warning", "warn", "pass", "ok", "unknown"}


def _descriptor_compat_rows(descriptor: dict) -> list[dict]:
    """Preserve legacy materialized descriptors without pretending physical verification."""
    output = dict(descriptor)
    provenance = {
        "source_id": descriptor.get("source_id"),
        "raw_artifact_id": descriptor.get("raw_artifact_id"),
        "raw_artifact_path": descriptor.get("raw_artifact_path"),
        "file_hash": descriptor.get("file_hash"),
        "ingestion_run_id": descriptor.get("ingestion_run_id"),
        "lineage_id": descriptor.get("lineage_id"),
        "raw_row_number": None,
        "physical_hash_verified": False,
        "materialization_mode": "descriptor_compat",
    }
    output["_provenance"] = {key: value for key, value in provenance.items() if value is not None}
    return [output]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    require_inputs(inputs, _REQUIRED_INPUTS)
    descriptors = records(inputs[_REQUIRED_INPUTS[0]], _REQUIRED_INPUTS[0])
    if not descriptors:
        raise ContractValidationError("readability_status_ok violation: validated handoff is empty")

    strict_physical = bool(config.get("strict_physical_validation", False))
    materialized_rows: list[dict] = []
    summaries: list[dict] = []
    formats_seen: set[str] = set()
    physical_verified_count = 0

    for descriptor in descriptors:
        readability = str(descriptor.get("readability_status") or "unknown").strip().lower()
        if readability not in _ALLOWED_READABILITY:
            raise ContractValidationError(
                f"readability_status_ok violation: source={descriptor.get('source_id')} status={readability}"
            )
        if not descriptor.get("lineage_id"):
            raise ContractValidationError("lineage_preserved violation: lineage_id is required")

        raw_path = descriptor.get("raw_artifact_path")
        if not raw_path:
            if strict_physical:
                raise ContractValidationError("P2_S1_M02_ARTIFACT_PATH_MISSING")
            compat_rows = _descriptor_compat_rows(descriptor)
            materialized_rows.extend(compat_rows)
            summaries.append(
                {
                    "source_id": descriptor.get("source_id"),
                    "raw_artifact_id": descriptor.get("raw_artifact_id"),
                    "materialization_mode": "descriptor_compat",
                    "physical_hash_verified": False,
                    "row_count": len(compat_rows),
                }
            )
            continue

        path = resolve_artifact_path(str(raw_path), config)
        if not path.exists() or not path.is_file():
            if strict_physical:
                raise ContractValidationError(f"P2_S1_M02_ARTIFACT_NOT_FOUND: {path}")
            compat_rows = _descriptor_compat_rows(descriptor)
            materialized_rows.extend(compat_rows)
            summaries.append(
                {
                    "source_id": descriptor.get("source_id"),
                    "raw_artifact_id": descriptor.get("raw_artifact_id"),
                    "raw_artifact_path": str(path),
                    "materialization_mode": "descriptor_compat",
                    "physical_hash_verified": False,
                    "row_count": len(compat_rows),
                    "warning": "artifact_not_accessible_in_compat_mode",
                }
            )
            continue

        max_file_bytes = config.get("max_file_bytes")
        file_size = path.stat().st_size
        if max_file_bytes is not None and file_size > int(max_file_bytes):
            raise ContractValidationError(
                f"P2_S1_M02_FILE_TOO_LARGE: {file_size} > configured max_file_bytes={max_file_bytes}"
            )
        declared_size = descriptor.get("file_size_bytes")
        if declared_size not in (None, "") and int(declared_size) != file_size:
            raise ContractValidationError(
                f"P2_S1_M02_FILE_SIZE_MISMATCH: declared={declared_size} observed={file_size}"
            )

        physical_hash = compute_sha256(path)
        declared_hash = descriptor.get("file_hash")
        hash_verified = False
        if declared_hash:
            if is_sha256(declared_hash):
                if physical_hash.lower() != str(declared_hash).lower():
                    raise ContractValidationError(
                        f"P2_S1_M02_PHYSICAL_HASH_MISMATCH: declared={declared_hash} observed={physical_hash}"
                    )
                hash_verified = True
            elif strict_physical:
                raise ContractValidationError(
                    f"P2_S1_M02_INVALID_DECLARED_HASH: expected SHA-256, got {declared_hash!r}"
                )

        format_name = detect_format(path, descriptor)
        formats_seen.add(format_name)
        parsed_rows = read_artifact_rows(path, format_name, config, descriptor)
        max_rows = config.get("max_rows_per_artifact")
        if max_rows is not None and len(parsed_rows) > int(max_rows):
            raise ContractValidationError(
                f"P2_S1_M02_TOO_MANY_ROWS: {len(parsed_rows)} > configured max_rows_per_artifact={max_rows}"
            )

        enriched_rows = [
            enrich_with_provenance(
                row,
                descriptor,
                row_number,
                physical_hash=physical_hash,
                hash_verified=hash_verified,
            )
            for row_number, row in enumerate(parsed_rows, start=1)
        ]
        materialized_rows.extend(enriched_rows)
        physical_verified_count += int(hash_verified)
        summaries.append(
            {
                "source_id": descriptor.get("source_id"),
                "raw_artifact_id": descriptor.get("raw_artifact_id"),
                "raw_artifact_path": str(path),
                "format": format_name,
                "file_size_bytes": file_size,
                "physical_file_hash": physical_hash,
                "physical_hash_verified": hash_verified,
                "materialization_mode": "physical",
                "row_count": len(enriched_rows),
            }
        )

    no_forbidden_rows(materialized_rows)
    result = artifact(
        "raw-artifact-read-bundle",
        materialized_rows,
        config,
        readability_status_ok=True,
        lineage_preserved=all(bool(row.get("lineage_id") or row.get("_provenance", {}).get("lineage_id")) for row in materialized_rows),
        artifacts_read=len(descriptors),
        rows_materialized=len(materialized_rows),
        physical_hashes_verified=physical_verified_count,
        formats_seen=sorted(formats_seen),
        artifact_summaries=summaries,
    )
    if materialized_rows and not result["lineage_preserved"]:
        raise ContractValidationError("lineage_preserved violation")

    return {
        "module_id": "P2.S1.M02",
        "module_name": "raw_artifact_reader",
        "phase": "phase_02_quality_pit",
        "subphase": "P2.S1",
        "contract": "P2_S1_M02_raw_artifact_reader.yaml",
        "required_inputs": _REQUIRED_INPUTS,
        "outputs": {"raw_artifact_read_bundle": result},
    }
