from __future__ import annotations

from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.document_rag.adapters import HashingEmbeddingProvider, InMemoryArtifactStore, JsonVectorStore
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S12_M01_document_chunker_and_indexer import run_module as indexer
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S12_M02_retrieval_index_manifest_builder import run_module as manifest_builder
from .test_p3_s12_m01_document_chunker_and_indexer import _inputs


def test_document_index_to_manifest_round_trip(root):
    inputs = _inputs(root)
    store = InMemoryArtifactStore()
    runtime = {"artifact_store": store, "embedding_provider": HashingEmbeddingProvider(), "vector_store": JsonVectorStore()}
    artifact = indexer(inputs, {"execution_profile": "TEST", "runtime": runtime})
    manifest = manifest_builder({"rag_index_artifact": artifact, "retrieval_config": inputs["retrieval_config"], "provider_adapter_registry_config": inputs["provider_adapter_registry_config"]}, {"execution_profile": "TEST", "runtime": {"artifact_store": store}})
    assert manifest["rag_index_artifact_hash"] == artifact["content_hash"]
    assert manifest["chunk_count"] == artifact["coverage"]["chunk_count"]
