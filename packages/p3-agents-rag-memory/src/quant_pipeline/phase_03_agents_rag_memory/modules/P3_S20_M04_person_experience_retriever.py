from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.s20.errors import (
    S20ContractError,
    S20Error,
)
from quant_pipeline.phase_03_agents_rag_memory.s20.service import run_m04

MODULE_ID = "P3.S20.M04"
LEGACY_ENTRYPOINT_DEPRECATED = True
CONTRACT = "modules/P3_S20_M04_person_experience_retriever.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
MODULE_NAME = 'person_experience_retriever'
SUBPHASE = 'P3.S20'
IMPLEMENTED = True
REQUIRED_INPUTS = (
    "person_retrieval_query_panel",
    "current_memory_state",
    "memory_access_policy",
    "context_learning_config",
)
PRODUCED_OUTPUTS = ('person_learning_trajectory_bundle',)


@deprecated_legacy_entrypoint("P3.S20.M04")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run P3.S20.M04 using only its declared contract inputs."""
    try:
        result = run_m04(inputs, config or {})
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
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))

