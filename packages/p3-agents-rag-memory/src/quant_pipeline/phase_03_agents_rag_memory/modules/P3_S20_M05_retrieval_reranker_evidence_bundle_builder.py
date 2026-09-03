from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.s20.errors import (
    S20ContractError,
    S20Error,
)
from quant_pipeline.phase_03_agents_rag_memory.s20.service import run_m05

MODULE_ID = "P3.S20.M05"
LEGACY_ENTRYPOINT_DEPRECATED = True
CONTRACT = "modules/P3_S20_M05_retrieval_reranker_evidence_bundle_builder.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
MODULE_NAME = 'retrieval_reranker_evidence_bundle_builder'
SUBPHASE = 'P3.S20'
IMPLEMENTED = True
REQUIRED_INPUTS = (
    "raw_retrieved_knowledge_bundle",
    "graph_retrieval_bundle",
    "person_learning_trajectory_bundle",
    "retrieval_config",
    "provider_adapter_registry_config",
)
PRODUCED_OUTPUTS = ('retrieved_knowledge_bundle', 'retrieval_evidence_map')


@deprecated_legacy_entrypoint("P3.S20.M05")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run P3.S20.M05 using only its declared contract inputs."""
    try:
        retrieved, evidence_map = run_m05(inputs, config or {})
    except S20Error:
        raise
    except Exception as exc:
        raise S20ContractError(
            f"{MODULE_ID} failed validation: {exc}"
        ) from exc
    return {
        "retrieved_knowledge_bundle": retrieved.model_dump(mode="json"),
        "retrieval_evidence_map": evidence_map.model_dump(mode="json"),
    }

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute reranking; LIVE requires an explicitly qualified reranker."""
    from ..s20.execution import service

    reranker_port = service(context, "reranker_port")
    retrieved, evidence_map = run_m05(
        dict(inputs),
        context.legacy_config(),
        reranker_port=reranker_port,
    )
    return {
        "retrieved_knowledge_bundle": retrieved.model_dump(mode="json"),
        "retrieval_evidence_map": evidence_map.model_dump(mode="json"),
    }

