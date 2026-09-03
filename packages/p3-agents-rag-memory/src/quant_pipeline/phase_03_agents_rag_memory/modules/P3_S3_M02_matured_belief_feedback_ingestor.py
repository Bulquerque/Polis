from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.learning_feedback.belief import (
    REQUIRED_INPUTS,
    ingest_matured_belief_feedback,
)

MODULE_ID = "P3.S3.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "matured_belief_feedback_ingestor"
PHASE = "phase_03_agents_rag_memory"
SUBPHASE = "P3.S3"
CONTRACT = "modules/P3_S3_M02_matured_belief_feedback_ingestor.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


@deprecated_legacy_entrypoint("P3.S3.M02")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and expose matured prior-cycle belief feedback."""
    output = ingest_matured_belief_feedback(inputs, config)
    return {
        "module_id": MODULE_ID,
        "module_name": MODULE_NAME,
        "phase": PHASE,
        "subphase": SUBPHASE,
        "contract": CONTRACT,
        "required_inputs": list(REQUIRED_INPUTS),
        "outputs": {"active_belief_feedback_bundle": output},
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



# Canonical Phase 3 module metadata.
REQUIRED_INPUTS = ('p9_belief_outcome_feedback_package', 'phase3_learning_feedback_handoff_manifest', 'phase3_run_snapshot')
PRODUCED_OUTPUTS = ('active_belief_feedback_bundle',)
