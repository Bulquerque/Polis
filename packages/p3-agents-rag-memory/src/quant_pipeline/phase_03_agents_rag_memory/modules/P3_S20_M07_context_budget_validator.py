from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.s20.errors import (
    S20ContractError,
    S20Error,
)
from quant_pipeline.phase_03_agents_rag_memory.s20.service import run_m07

MODULE_ID = "P3.S20.M07"
LEGACY_ENTRYPOINT_DEPRECATED = True
CONTRACT = "modules/P3_S20_M07_context_budget_validator.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
MODULE_NAME = 'context_budget_validator'
SUBPHASE = 'P3.S20'
IMPLEMENTED = True
REQUIRED_INPUTS = (
    "person_context_bundle",
    "context_budget_config",
    "model_knowledge_cutoff_report",
)
PRODUCED_OUTPUTS = ('validated_person_context_bundle',)


@deprecated_legacy_entrypoint("P3.S20.M07")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run P3.S20.M07 using only its declared contract inputs."""
    try:
        result = run_m07(inputs, config or {})
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
    """Validate the final budget with the exact LIVE tokenizer."""
    from ..s20.execution import service

    tokenizer_port = service(context, "tokenizer_port")
    result = run_m07(
        dict(inputs),
        context.legacy_config(),
        tokenizer_port=tokenizer_port,
    )
    return result.model_dump(mode="json")

