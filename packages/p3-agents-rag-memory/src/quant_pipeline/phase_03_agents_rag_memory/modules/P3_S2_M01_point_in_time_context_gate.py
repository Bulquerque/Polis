from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.temporal_authority.pit import apply_point_in_time_gate

MODULE_ID = "P3.S2.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "point_in_time_context_gate"
PHASE = "phase_03_agents_rag_memory"
SUBPHASE = "P3.S2"
CONTRACT = "modules/P3_S2_M01_point_in_time_context_gate.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = ("validated_context_inputs", "evaluation_window_config")
PRODUCED_OUTPUTS = ('pit_validated_context',)


@deprecated_legacy_entrypoint("P3.S2.M01")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output = apply_point_in_time_gate(inputs, config)
    return {
        "module_id": MODULE_ID,
        "module_name": MODULE_NAME,
        "phase": PHASE,
        "subphase": SUBPHASE,
        "contract": CONTRACT,
        "required_inputs": list(REQUIRED_INPUTS),
        "outputs": {"pit_validated_context": output},
        "implementation_status": IMPLEMENTATION_STATUS,
        "production_promotion_allowed": False,
    }

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))

