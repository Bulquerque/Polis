from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.s20.errors import (
    S20ContractError,
    S20Error,
)
from quant_pipeline.phase_03_agents_rag_memory.s20.service import run_m03

MODULE_ID = "P3.S20.M03"
LEGACY_ENTRYPOINT_DEPRECATED = True
CONTRACT = "modules/P3_S20_M03_graph_rag_query_executor.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
MODULE_NAME = 'graph_rag_query_executor'
SUBPHASE = 'P3.S20'
IMPLEMENTED = True
REQUIRED_INPUTS = (
    "person_retrieval_query_panel",
    "graph_rag_artifact",
    "graph_evidence_map",
    "graph_config",
    "provider_adapter_registry_config",
)
PRODUCED_OUTPUTS = ('graph_retrieval_bundle',)


@deprecated_legacy_entrypoint("P3.S20.M03")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run P3.S20.M03 using only its declared contract inputs."""
    try:
        result = run_m03(inputs, config or {})
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
    """Execute bounded graph retrieval through an injected LIVE query port."""
    from ..s20.execution import service

    graph_query_port = service(context, "graph_query_port")
    result = run_m03(
        dict(inputs),
        context.legacy_config(),
        graph_query_port=graph_query_port,
    )
    return result.model_dump(mode="json")

