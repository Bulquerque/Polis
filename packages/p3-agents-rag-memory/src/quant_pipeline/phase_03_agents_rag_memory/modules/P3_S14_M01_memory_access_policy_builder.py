from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.foundation.memory.service import MemoryPolicyBuilder

MODULE_ID = "P3.S14.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
CONTRACT = "modules/P3_S14_M01_memory_access_policy_builder.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = ("memory_access_config", "person_schema_policy", "phase3_run_snapshot")
PRODUCED_OUTPUTS = ("memory_access_policy",)


@deprecated_legacy_entrypoint("P3.S14.M01")
def run_module(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    missing = [name for name in REQUIRED_INPUTS if name not in inputs]
    if missing:
        raise ValueError(f"P3.S14.M01 missing inputs: {missing}")
    service = context.get("memory_policy_builder")
    if not isinstance(service, MemoryPolicyBuilder):
        raise ValueError("context.memory_policy_builder must be a configured MemoryPolicyBuilder")
    result = service.run(**{name: inputs[name] for name in REQUIRED_INPUTS})
    return {"memory_access_policy": result.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
MODULE_NAME = 'memory_access_policy_builder'
SUBPHASE = 'P3.S14'
