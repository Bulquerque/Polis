from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ExecutionProfile, ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.s20.errors import (
    S20ContractError,
    S20Error,
)
from quant_pipeline.phase_03_agents_rag_memory.s20.service import run_m02

MODULE_ID = "P3.S20.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
CONTRACT = "modules/P3_S20_M02_hybrid_memory_rag_retriever.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
MODULE_NAME = 'hybrid_memory_rag_retriever'
SUBPHASE = 'P3.S20'
IMPLEMENTED = True
REQUIRED_INPUTS = (
    "person_retrieval_query_panel",
    "memory_index_manifest",
    "retrieval_index_manifest",
    "memory_access_policy",
    "retrieval_config",
    "provider_adapter_registry_config",
)
PRODUCED_OUTPUTS = ('raw_retrieved_knowledge_bundle',)


@deprecated_legacy_entrypoint("P3.S20.M02")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run P3.S20.M02 using only its declared contract inputs."""
    try:
        result = run_m02(inputs, config or {})
    except S20Error:
        raise
    except Exception as exc:
        raise S20ContractError(
            f"{MODULE_ID} failed validation: {exc}"
        ) from exc
    return result.model_dump(mode="json")

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute retrieval with profile-qualified memory and knowledge ports."""
    from ..s20.execution import service

    memory_port = service(
        context,
        "memory_port",
        required_in=(ExecutionProfile.REPLAY, ExecutionProfile.LIVE),
    )
    knowledge_port = service(
        context,
        "knowledge_port",
        required_in=(ExecutionProfile.REPLAY, ExecutionProfile.LIVE),
    )
    result = run_m02(
        dict(inputs),
        context.legacy_config(),
        memory_port=memory_port,
        knowledge_port=knowledge_port,
    )
    return result.model_dump(mode="json")

