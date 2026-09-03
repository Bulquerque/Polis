from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from ..runtime.state_transition import guard_gradual_changes
from ..runtime_shared.s23_models import CurrentPersonStatePanel, NextPersonStatePanel, PersonSchemaPolicy, StateChangeConfig
from ._s23_wrapper import parse_model

MODULE_ID = "P3.S23.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "gradual_change_guard"
SUBPHASE = "P3.S23"
CONTRACT = "modules/P3_S23_M02_gradual_change_guard.yaml"
REQUIRED_INPUTS = [
    "next_person_state_panel",
    "current_person_state_panel",
    "person_schema_policy",
    "state_change_config",
]
PRODUCED_OUTPUTS = ('validated_next_person_state_panel',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S23.M02")
def run_module(inputs: Mapping[str, object], config: Mapping[str, object] | None = None) -> dict[str, object]:
    del config
    output = guard_gradual_changes(
        candidates=parse_model(inputs, "next_person_state_panel", NextPersonStatePanel, module_id=MODULE_ID),
        current_states=parse_model(inputs, "current_person_state_panel", CurrentPersonStatePanel, module_id=MODULE_ID),
        person_policy=parse_model(inputs, "person_schema_policy", PersonSchemaPolicy, module_id=MODULE_ID),
        config=parse_model(inputs, "state_change_config", StateChangeConfig, module_id=MODULE_ID),
    )
    return {"validated_next_person_state_panel": output.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
