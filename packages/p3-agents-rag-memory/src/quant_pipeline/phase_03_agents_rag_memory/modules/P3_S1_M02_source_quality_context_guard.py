from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.governance.intake import apply_source_quality_policy

MODULE_ID = "P3.S1.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "source_quality_context_guard"
PHASE = "phase_03_agents_rag_memory"
SUBPHASE = "P3.S1"
CONTRACT = "modules/P3_S1_M02_source_quality_context_guard.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"

REQUIRED_INPUTS = (
    "validated_phase2_handoff",
    "source_quality_panel",
    "source_quality_policy_config",
)
PRODUCED_OUTPUTS = ('validated_context_inputs',)


@deprecated_legacy_entrypoint("P3.S1.M02")
def run_module(inputs: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    output = apply_source_quality_policy(inputs, config)
    return {
        "module_id": MODULE_ID,
        "module_name": MODULE_NAME,
        "phase": PHASE,
        "subphase": SUBPHASE,
        "contract": CONTRACT,
        "required_inputs": list(REQUIRED_INPUTS),
        "outputs": {"validated_context_inputs": output},
        "implementation_status": "IMPLEMENTED_QUALIFIED_INTERNAL",
        "production_promotion_allowed": False,
    }

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))

