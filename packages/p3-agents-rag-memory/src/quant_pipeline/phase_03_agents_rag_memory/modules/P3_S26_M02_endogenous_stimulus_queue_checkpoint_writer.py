from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext
from collections.abc import Mapping
from typing import Any
from ..s26.entrypoints import prepare_inputs,run_guarded
from ..s26.queue import build_next_cycle_queue
MODULE_ID="P3.S26.M02"; MODULE_NAME="endogenous_stimulus_queue_checkpoint_writer"; SUBPHASE="P3.S26"; CONTRACT="modules/P3_S26_M02_endogenous_stimulus_queue_checkpoint_writer.yaml"; IMPLEMENTED=True; IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS=("tool_discovery_event_panel","social_delivery_event_panel","memory_trigger_event_panel","finalized_attention_followup_intent_panel","phase3_run_snapshot","stimulus_bus_config")
PRODUCED_OUTPUTS = ('next_cycle_endogenous_stimulus_queue',)
MODULE_ID = 'P3.S26.M02'
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = 'endogenous_stimulus_queue_checkpoint_writer'
SUBPHASE = 'P3.S26'
CONTRACT = 'modules/P3_S26_M02_endogenous_stimulus_queue_checkpoint_writer.yaml'
REQUIRED_INPUTS = ['tool_discovery_event_panel', 'social_delivery_event_panel', 'memory_trigger_event_panel', 'finalized_attention_followup_intent_panel', 'phase3_run_snapshot', 'stimulus_bus_config']

@deprecated_legacy_entrypoint("P3.S26.M02")
def run_module(inputs: Mapping[str,Any],config: Mapping[str,Any]|None=None)->dict[str,Any]:
    values=prepare_inputs(module_id=MODULE_ID,inputs=inputs,required=REQUIRED_INPUTS,config_key="stimulus_bus_config",config=config)
    return run_guarded(MODULE_ID,lambda:{"next_cycle_endogenous_stimulus_queue":build_next_cycle_queue(**values).model_dump(mode="json")})

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
