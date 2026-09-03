from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..s31_products import build_p9_context_learning_handoff

MODULE_ID = "P3.S31.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "p9_context_learning_handoff_builder"
SUBPHASE = "P3.S31"
CONTRACT = "modules/P3_S31_M02_p9_context_learning_handoff_builder.yaml"
REQUIRED_INPUTS = (
    "p9_evaluation_evidence_bundle",
    "phase4_social_handoff_manifest",
    "variable_evolution_input_manifest",
    "phase3_run_snapshot",
)
PRODUCED_OUTPUTS = ('p9_context_learning_handoff_manifest',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S31.M02")
def run_module(inputs: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    context = config.get("execution_context")
    if not isinstance(context, dict):
        raise ValueError("P3.S31.M02 requires an explicit deterministic execution context")
    compatibility = config.get("p9_consumer_compatibility")
    if not isinstance(compatibility, dict):
        raise ValueError("P3.S31.M02 requires p9_consumer_compatibility in config")
    return build_p9_context_learning_handoff(inputs, context, compatibility)

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
