from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..s30_products import build_variable_evolution_handoff

MODULE_ID = "P3.S30.M05"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "variable_evolution_handoff_builder"
SUBPHASE = "P3.S30"
CONTRACT = "modules/P3_S30_M05_variable_evolution_handoff_builder.yaml"
REQUIRED_INPUTS = (
    "validated_society_state_panel",
    "social_feature_panel",
    "context_memory_feature_panel",
    "hypothesis_registry",
    "belief_outcome_commitment_log",
    "phase3_run_snapshot",
)
PRODUCED_OUTPUTS = ('variable_evolution_input_manifest',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S30.M05")
def run_module(inputs: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    context = config.get("execution_context")
    if not isinstance(context, dict):
        raise ValueError("P3.S30.M05 requires an explicit deterministic execution context")
    return build_variable_evolution_handoff(inputs, context)

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
