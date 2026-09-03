from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.temporal_authority.cutoff import classify_model_knowledge_cutoff

MODULE_ID = "P3.S2.M03"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "model_knowledge_cutoff_firewall"
PHASE = "phase_03_agents_rag_memory"
SUBPHASE = "P3.S2"
CONTRACT = "modules/P3_S2_M03_model_knowledge_cutoff_firewall.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = (
    "phase3_run_snapshot",
    "provider_adapter_registry_config",
    "evaluation_protocol_config",
    "model_knowledge_cutoff_policy_config",
)
PRODUCED_OUTPUTS = ('model_knowledge_cutoff_report',)


@deprecated_legacy_entrypoint("P3.S2.M03")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output = classify_model_knowledge_cutoff(inputs, config)
    return {
        "module_id": MODULE_ID,
        "module_name": MODULE_NAME,
        "phase": PHASE,
        "subphase": SUBPHASE,
        "contract": CONTRACT,
        "required_inputs": list(REQUIRED_INPUTS),
        "outputs": {"model_knowledge_cutoff_report": output},
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

