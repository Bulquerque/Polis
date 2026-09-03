from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from ..runtime.state_transition import write_person_state_transition
from ..runtime_shared.s22_models import CurrentBeliefStatePanel, EvidenceBoundBeliefUpdatePanel
from ..runtime_shared.s23_models import CurrentPersonStatePanel, PersonSchemaPolicy, StateChangeConfig
from ._s23_wrapper import parse_model

MODULE_ID = "P3.S23.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "person_state_transition_writer"
SUBPHASE = "P3.S23"
CONTRACT = "modules/P3_S23_M01_person_state_transition_writer.yaml"
REQUIRED_INPUTS = [
    "evidence_bound_belief_update_panel",
    "current_person_state_panel",
    "current_belief_state_panel",
    "person_schema_policy",
    "state_change_config",
]
PRODUCED_OUTPUTS = ('next_person_state_panel', 'next_belief_state_panel')
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S23.M01")
def run_module(inputs: Mapping[str, object], config: Mapping[str, object] | None = None) -> dict[str, object]:
    del config
    person_panel, belief_panel = write_person_state_transition(
        belief_updates=parse_model(inputs, "evidence_bound_belief_update_panel", EvidenceBoundBeliefUpdatePanel, module_id=MODULE_ID),
        current_person_states=parse_model(inputs, "current_person_state_panel", CurrentPersonStatePanel, module_id=MODULE_ID),
        current_beliefs=parse_model(inputs, "current_belief_state_panel", CurrentBeliefStatePanel, module_id=MODULE_ID),
        person_policy=parse_model(inputs, "person_schema_policy", PersonSchemaPolicy, module_id=MODULE_ID),
        config=parse_model(inputs, "state_change_config", StateChangeConfig, module_id=MODULE_ID),
    )
    return {
        "next_person_state_panel": person_panel.model_dump(mode="json"),
        "next_belief_state_panel": belief_panel.model_dump(mode="json"),
    }

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
