from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.temporal_graphrag.adapters import (
    FileArtifactStore,
    ListEventSink,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.temporal_graphrag.errors import ContractError
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.temporal_graphrag.canonical import content_hash
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.temporal_graphrag.models import (
    ArtifactStatus,
    CapabilityStatus,
    GraphConfig,
    IndexComponent,
    PitValidatedContext,
    ProviderRegistry,
    RagCoverage,
    RagIndexArtifact,
    RunSnapshot,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.temporal_graphrag.module_m01 import compute_artifact_hash
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S13_M01_temporal_graph_builder import run_module as run_m01
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S13_M02_graph_evidence_linker import run_module as run_m02

AS_OF = datetime(2026, 1, 1, tzinfo=UTC)


def _empty_component(name: str) -> IndexComponent:
    return IndexComponent(
        name=name,
        status=CapabilityStatus.NOT_APPLICABLE,
        artifact_ref=None,
        adapter_id="none",
        adapter_version="1.0.0",
        record_count=0,
        qualification_status="NOT_APPLICABLE",
    )


def _rag_index() -> dict[str, object]:
    base = {
        "artifact_name": "rag_index_artifact",
        "schema_id": "rag_index_artifact.v2",
        "schema_version": "2.0.0",
        "artifact_id": "rag_empty",
        "run_id": "run_s13",
        "snapshot_id": "snap_s13",
        "as_of_time": AS_OF,
        "lineage_id": "lineage_s13",
        "status": ArtifactStatus.EMPTY,
        "reason_code": "EMPTY_CORPUS",
        "grain": ("chunk_id",),
        "primary_key": ("chunk_id",),
        "chunk_schema_id": "rag_chunk.v1",
        "chunk_catalog": _empty_component("chunk_catalog"),
        "keyword_index": _empty_component("keyword_index"),
        "vector_index": _empty_component("vector_index"),
        "coverage": RagCoverage(
            source_count=0,
            document_count=0,
            chunk_count=0,
            rejected_document_count=0,
            rejected_chunk_count=0,
        ),
        "configuration_hash": "a" * 64,
        "provider_fingerprints": {},
        "issues": (),
    }
    digest = compute_artifact_hash(base)
    return RagIndexArtifact(content_hash=digest, **base).model_dump(mode="json")


def _inputs() -> dict[str, object]:
    graph_config = {
        "schema_id": "p3_s13_graph_config.v2",
        "schema_version": "2.0.0",
        "provider_proposals": {"enabled": False, "required": False},
        "publication": {"enabled": False, "required": False},
    }
    return {
        "rag_index_artifact": _rag_index(),
        "pit_validated_context": PitValidatedContext(
            schema_id="pit_context.v1",
            schema_version="1.0.0",
            records=(),
            lineage_id="lineage_s13",
        ).model_dump(mode="json"),
        "phase3_run_snapshot": RunSnapshot(
            schema_id="phase3_run_snapshot.v1",
            schema_version="1.0.0",
            run_id="run_s13",
            snapshot_id="snap_s13",
            as_of_time=AS_OF,
            pipeline_version="RC4.1",
            architecture_revision="P3-FINAL",
            config_hashes={"graph_config": content_hash(GraphConfig.model_validate(graph_config))},
            provider_fingerprints={},
        ).model_dump(mode="json"),
        "graph_config": graph_config,
        "provider_adapter_registry_config": ProviderRegistry(
            schema_id="provider_registry.v1",
            schema_version="1.0.0",
            providers=(),
        ).model_dump(mode="json"),
    }


def test_live_profile_fails_closed_without_persistent_store() -> None:
    with pytest.raises(ContractError, match="PERSISTENT_STORE_REQUIRED"):
        run_m01(_inputs(), {"execution_profile": "LIVE"})


def test_graph_build_and_evidence_link_roundtrip_in_live_profile(tmp_path: Path) -> None:
    store = FileArtifactStore(tmp_path / "graph")
    runtime = {"artifact_store": store, "event_sink": ListEventSink()}
    inputs = _inputs()

    graph = run_m01(
        inputs,
        {"execution_profile": "LIVE", "runtime": runtime},
    )
    assert graph["status"] == "EMPTY"
    assert graph["coverage"]["node_count"] == 0

    evidence = run_m02(
        {
            "graph_rag_artifact": graph,
            "rag_index_artifact": inputs["rag_index_artifact"],
            "graph_config": inputs["graph_config"],
        },
        {"execution_profile": "LIVE", "runtime": runtime},
    )
    assert evidence["status"] == "EMPTY"
    assert evidence["coverage"]["coverage_ratio"] == 1.0


def test_graph_builder_rejects_undeclared_missing_snapshot() -> None:
    inputs = _inputs()
    inputs.pop("phase3_run_snapshot")
    with pytest.raises(ContractError, match="INPUT_INVALID"):
        run_m01(inputs, {"execution_profile": "TEST"})
