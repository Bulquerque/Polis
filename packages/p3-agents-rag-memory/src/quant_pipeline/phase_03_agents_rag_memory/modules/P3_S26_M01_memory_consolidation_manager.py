from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext
from collections.abc import Mapping
from typing import Any
from ..s26.entrypoints import prepare_inputs,run_guarded
from ..s26.memory import consolidate_memory
MODULE_ID="P3.S26.M01"; MODULE_NAME="memory_consolidation_manager"; SUBPHASE="P3.S26"; CONTRACT="modules/P3_S26_M01_memory_consolidation_manager.yaml"; IMPLEMENTED=True; IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS=("current_memory_state","person_learning_trajectory_bundle","next_belief_state_panel","validated_next_person_state_panel","social_delivery_panel","active_belief_feedback_bundle","active_retro_policy_patch","memory_consolidation_config")
PRODUCED_OUTPUTS = ('next_memory_state', 'memory_trigger_event_panel')
MODULE_ID = 'P3.S26.M01'
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = 'memory_consolidation_manager'
SUBPHASE = 'P3.S26'
CONTRACT = 'modules/P3_S26_M01_memory_consolidation_manager.yaml'
REQUIRED_INPUTS = ['current_memory_state', 'person_learning_trajectory_bundle', 'next_belief_state_panel', 'validated_next_person_state_panel', 'social_delivery_panel', 'active_belief_feedback_bundle', 'active_retro_policy_patch', 'memory_consolidation_config']

@deprecated_legacy_entrypoint("P3.S26.M01")
def run_module(inputs: Mapping[str,Any],config: Mapping[str,Any]|None=None)->dict[str,Any]:
    values=prepare_inputs(module_id=MODULE_ID,inputs=inputs,required=REQUIRED_INPUTS,config_key="memory_consolidation_config",config=config)
    def operation():
        memory,triggers=consolidate_memory(**values)
        return {"next_memory_state":memory.model_dump(mode="json"),"memory_trigger_event_panel":triggers.model_dump(mode="json")}
    return run_guarded(MODULE_ID,operation)

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
