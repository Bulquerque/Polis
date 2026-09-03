from __future__ import annotations

from datetime import UTC, datetime
import pytest
import yaml

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S12_M01_document_chunker_and_indexer import run_module


def _inputs(root):
    providers = yaml.safe_load((root / "config/resources/s12/provider_adapter_registry.example.yaml").read_text())
    retrieval = yaml.safe_load((root / "config/resources/s12/retrieval_config.yaml").read_text())
    fingerprint = providers["providers"][0]["fingerprint"]
    return {
        "pit_validated_context": {
            "schema_id": "pit_validated_context.s12.v1",
            "schema_version": "1.0.0",
            "lineage_id": "lineage-s12-test",
            "records": [{
                "record_type": "document",
                "document_id": "doc-1",
                "source_id": "source-1",
                "content": "A company reported higher revenue and lower leverage in the quarter.",
                "event_time": "2025-12-01T00:00:00Z",
                "effective_time": "2025-12-01T00:00:00Z",
                "available_at": "2025-12-02T00:00:00Z",
                "ingested_at": "2025-12-02T01:00:00Z",
                "source_quality": 0.9,
                "entities": ["company-1"],
                "underlyings": ["COMP1"],
                "metadata": {},
                "lineage_refs": ["lineage-doc-1"],
            }],
        },
        "phase3_run_snapshot": {
            "schema_id": "phase3_run_snapshot.s12.v1",
            "schema_version": "1.0.0",
            "run_id": "run-s12",
            "snapshot_id": "snapshot-s12",
            "as_of_time": "2026-01-01T00:00:00Z",
            "pipeline_version": "RC4.1",
            "architecture_revision": "P3-FINAL",
            "config_hashes": {},
            "provider_fingerprints": {"offline_hashing": fingerprint},
            "timezone": "UTC",
        },
        "retrieval_config": retrieval,
        "provider_adapter_registry_config": providers,
    }


def test_document_index_is_deterministic_in_test_profile(root):
    inputs = _inputs(root)
    first = run_module(inputs, {"execution_profile": "TEST"})
    second = run_module(inputs, {"execution_profile": "TEST"})
    assert first["content_hash"] == second["content_hash"]
    assert first["coverage"]["document_count"] == 1
    assert first["coverage"]["chunk_count"] >= 1


def test_live_profile_requires_injected_qualified_dependencies(root):
    with pytest.raises(RuntimeError, match="requires injected"):
        run_module(_inputs(root), {"execution_profile": "LIVE"})
