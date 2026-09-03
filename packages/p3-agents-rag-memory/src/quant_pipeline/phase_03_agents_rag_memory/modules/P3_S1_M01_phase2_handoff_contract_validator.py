from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.governance.intake import REQUIRED_INPUTS, validate_phase2_handoff

MODULE_ID = "P3.S1.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "phase2_handoff_contract_validator"
PHASE = "phase_03_agents_rag_memory"
SUBPHASE = "P3.S1"
CONTRACT = "modules/P3_S1_M01_phase2_handoff_contract_validator.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


@deprecated_legacy_entrypoint("P3.S1.M01")
def run_module(inputs: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    output = validate_phase2_handoff(inputs, config)
    return {
        "module_id": MODULE_ID,
        "module_name": MODULE_NAME,
        "phase": PHASE,
        "subphase": SUBPHASE,
        "contract": CONTRACT,
        "required_inputs": list(REQUIRED_INPUTS),
        "outputs": {"validated_phase2_handoff": output},
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



# Canonical Phase 3 module metadata.
REQUIRED_INPUTS = ('clean_context_source_panel', 'clean_document_panel', 'clean_event_reference_panel', 'source_quality_panel', 'context_handoff_manifest', 'phase3_handoff_manifest')
PRODUCED_OUTPUTS = ('validated_phase2_handoff',)
