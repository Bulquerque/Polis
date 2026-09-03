from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext
from collections.abc import Mapping
from typing import Any
from ..s26.checkpoint import build_cycle_checkpoint
from ..s26.entrypoints import prepare_inputs,run_guarded
MODULE_ID="P3.S26.M03"; MODULE_NAME="cycle_state_checkpoint_writer"; SUBPHASE="P3.S26"; CONTRACT="modules/P3_S26_M03_cycle_state_checkpoint_writer.yaml"; IMPLEMENTED=True; IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS=("validated_next_person_state_panel","next_belief_state_panel","next_memory_state","next_social_graph","next_cycle_endogenous_stimulus_queue","phase3_run_snapshot","belief_outcome_commitment_log")
PRODUCED_OUTPUTS = ('cycle_state_snapshot_out',)
MODULE_ID = 'P3.S26.M03'
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = 'cycle_state_checkpoint_writer'
SUBPHASE = 'P3.S26'
CONTRACT = 'modules/P3_S26_M03_cycle_state_checkpoint_writer.yaml'
REQUIRED_INPUTS = ['validated_next_person_state_panel', 'next_belief_state_panel', 'next_memory_state', 'next_social_graph', 'next_cycle_endogenous_stimulus_queue', 'phase3_run_snapshot', 'belief_outcome_commitment_log']

@deprecated_legacy_entrypoint("P3.S26.M03")
def run_module(inputs: Mapping[str,Any],config: Mapping[str,Any]|None=None)->dict[str,Any]:
    values=prepare_inputs(module_id=MODULE_ID,inputs=inputs,required=REQUIRED_INPUTS,config_key=None,config=config)
    return run_guarded(MODULE_ID,lambda:{"cycle_state_snapshot_out":build_cycle_checkpoint(**values).model_dump(mode="json")})

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
