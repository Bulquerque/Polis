from __future__ import annotations

from copy import deepcopy

import pytest

from .support_s33 import build_s33_m01, build_s33_m02, digest, p1_inputs


def test_m02_authorizes_only_p1_refs_linked_to_p2_sources():
    out = build_s33_m02()
    records = out["phase1_raw_evidence_reference_index"]["records"]
    assert len(records) == 3
    assert all(item["custody_status"] == "AUTHORIZED" for item in records)
    assert all(item["linked_p2_artifact_ids"] for item in records)


def test_m02_never_exposes_storage_path():
    out = build_s33_m02()
    text = str(out)
    assert "raw/sec/snapshot.json" not in text
    assert all(len(item["storage_ref_token"]) == 64 for item in out["phase1_raw_evidence_reference_index"]["records"])


def test_m02_marks_orphan_source_as_unauthorized():
    inputs = p1_inputs()
    inputs["source_snapshot_registry"]["records"].append({
        "source_id": "orphan",
        "ingestion_run_id": "ingestion-x",
        "raw_artifact_id": "raw-orphan",
        "raw_artifact_path": "raw/orphan/file.json",
        "file_hash": digest("raw-orphan"),
        "file_size_bytes": 1,
        "ingested_at": "2024-01-10T10:00:00Z",
        "declared_available_at": "2024-01-10T09:00:00Z",
        "readability_status": "READABLE",
    })
    inputs["raw_file_inventory"]["records"].append({"raw_artifact_id": "raw-orphan", "file_hash": digest("raw-orphan")})
    out = build_s33_m02(build_s33_m01(), inputs)
    orphan = next(item for item in out["phase1_raw_evidence_reference_index"]["records"] if item["raw_artifact_id"] == "raw-orphan")
    assert orphan["custody_status"] == "UNAUTHORIZED_ORPHAN"


def test_m02_detects_inventory_hash_mismatch():
    inputs = p1_inputs()
    inputs["raw_file_inventory"]["records"][0]["file_hash"] = "0" * 64
    out = build_s33_m02(build_s33_m01(), inputs)
    assert any(item["custody_status"] == "HASH_MISMATCH" for item in out["phase1_raw_evidence_reference_index"]["records"])


def test_m02_rejects_traversal_metadata():
    inputs = p1_inputs()
    inputs["source_snapshot_registry"]["records"][0]["raw_artifact_path"] = "../secret"
    with pytest.raises(ValueError, match="traversal"):
        build_s33_m02(build_s33_m01(), inputs)


def test_m02_rejects_duplicate_raw_artifact_id():
    inputs = p1_inputs()
    inputs["source_snapshot_registry"]["records"].append(deepcopy(inputs["source_snapshot_registry"]["records"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        build_s33_m02(build_s33_m01(), inputs)
