from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.s20.errors import (
    S20ContractError,
    S20Error,
)
from quant_pipeline.phase_03_agents_rag_memory.s20.service import run_m06

MODULE_ID = "P3.S20.M06"
LEGACY_ENTRYPOINT_DEPRECATED = True
CONTRACT = "modules/P3_S20_M06_person_context_assembler.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
MODULE_NAME = 'person_context_assembler'
SUBPHASE = 'P3.S20'
IMPLEMENTED = True
REQUIRED_INPUTS = (
    "cognitive_cycle_schedule",
    "stimulus_panel",
    "activation_panel",
    "current_person_state_panel",
    "current_belief_state_panel",
    "retrieved_knowledge_bundle",
    "current_social_graph",
    "person_tool_entitlement_panel",
    "active_retro_policy_patch",
)
PRODUCED_OUTPUTS = ('person_context_bundle',)


@deprecated_legacy_entrypoint("P3.S20.M06")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run P3.S20.M06 using only its declared contract inputs."""
    try:
        result = run_m06(inputs)
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
    """Assemble context with the model tokenizer required for LIVE runs."""
    from ..s20.execution import service

    tokenizer_port = service(context, "tokenizer_port")
    result = run_m06(dict(inputs), tokenizer_port=tokenizer_port)
    return result.model_dump(mode="json")

