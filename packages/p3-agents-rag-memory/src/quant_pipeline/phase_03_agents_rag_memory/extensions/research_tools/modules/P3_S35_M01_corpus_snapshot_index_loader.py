from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.corpus.snapshot import (
    CorpusSnapshotIndexLoader,
)

MODULE_ID = "P3.S35.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "corpus_snapshot_index_loader"
SUBPHASE = "P3.S35"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_LOCAL"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S35_M01_corpus_snapshot_index_loader.yaml"
REQUIRED_INPUTS = ("retrieval_index_manifest", "phase3_run_snapshot")
OPTIONAL_INPUTS = ("document_metadata",)
PRODUCED_OUTPUTS = ("corpus_index_snapshot", "corpus_index_readiness_report")


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    artifact_store = context.services.get("artifact_store")
    if artifact_store is None:
        raise RuntimeError("P3.S35.M01 requires service 'artifact_store'")
    result = CorpusSnapshotIndexLoader(artifact_store).load(
        retrieval_manifest=inputs["retrieval_index_manifest"],
        phase3_run_snapshot=inputs["phase3_run_snapshot"],
        document_metadata=inputs.get("document_metadata"),
    )
    return {
        "corpus_index_snapshot": result.snapshot.model_dump(mode="json"),
        "corpus_index_readiness_report": result.readiness.model_dump(mode="json"),
    }
