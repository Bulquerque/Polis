from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..s31_products import build_p9_evaluation_evidence_bundle

MODULE_ID = "P3.S31.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "p9_evaluation_evidence_bundle_builder"
SUBPHASE = "P3.S31"
CONTRACT = "modules/P3_S31_M01_p9_evaluation_evidence_bundle_builder.yaml"
REQUIRED_INPUTS = (
    "phase4_social_handoff_manifest",
    "variable_evolution_input_manifest",
    "belief_outcome_commitment_log",
    "model_knowledge_cutoff_report",
    "phase3_run_snapshot",
    "validated_society_state_panel",
)
PRODUCED_OUTPUTS = ('p9_evaluation_evidence_bundle',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S31.M01")
def run_module(inputs: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    context = config.get("execution_context")
    if not isinstance(context, dict):
        raise ValueError("P3.S31.M01 requires an explicit deterministic execution context")
    return build_p9_evaluation_evidence_bundle(inputs, context)

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
