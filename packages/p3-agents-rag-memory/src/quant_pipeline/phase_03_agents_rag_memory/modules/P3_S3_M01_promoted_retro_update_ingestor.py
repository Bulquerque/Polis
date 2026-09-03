from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.learning_feedback.retro import (
    REQUIRED_INPUTS,
    ingest_promoted_retro_update,
)

MODULE_ID = "P3.S3.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "promoted_retro_update_ingestor"
PHASE = "phase_03_agents_rag_memory"
SUBPHASE = "P3.S3"
CONTRACT = "modules/P3_S3_M01_promoted_retro_update_ingestor.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


@deprecated_legacy_entrypoint("P3.S3.M01")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and expose a promoted retro patch without applying it."""
    output = ingest_promoted_retro_update(inputs, config)
    return {
        "module_id": MODULE_ID,
        "module_name": MODULE_NAME,
        "phase": PHASE,
        "subphase": SUBPHASE,
        "contract": CONTRACT,
        "required_inputs": list(REQUIRED_INPUTS),
        "outputs": {"active_retro_policy_patch": output},
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
REQUIRED_INPUTS = ('retro_memory_update_package', 'phase3_retro_handoff_manifest', 'phase3_run_snapshot', 'retro_patch_compatibility_config')
PRODUCED_OUTPUTS = ('active_retro_policy_patch',)
