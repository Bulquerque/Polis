from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from ..runtime.social_delivery import route_social_messages
from ..runtime_shared.s21_models import FinalizedSocialIntentPanel
from ..runtime_shared.s23_models import ValidatedNextPersonStatePanel
from ..runtime_shared.s24_models import CurrentSocialGraph, SocialDeliveryConfig
from ._s24_wrapper import parse_model

MODULE_ID = "P3.S24.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "social_message_router"
SUBPHASE = "P3.S24"
CONTRACT = "modules/P3_S24_M01_social_message_router.yaml"
REQUIRED_INPUTS = [
    "finalized_social_intent_panel",
    "current_social_graph",
    "validated_next_person_state_panel",
    "social_delivery_config",
]
PRODUCED_OUTPUTS = ('social_message_panel',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S24.M01")
def run_module(inputs: Mapping[str, object], config: Mapping[str, object] | None = None) -> dict[str, object]:
    del config
    output = route_social_messages(
        intents=parse_model(inputs, "finalized_social_intent_panel", FinalizedSocialIntentPanel, module_id=MODULE_ID),
        social_graph=parse_model(inputs, "current_social_graph", CurrentSocialGraph, module_id=MODULE_ID),
        next_person_states=parse_model(inputs, "validated_next_person_state_panel", ValidatedNextPersonStatePanel, module_id=MODULE_ID),
        config=parse_model(inputs, "social_delivery_config", SocialDeliveryConfig, module_id=MODULE_ID),
    )
    return {"social_message_panel": output.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
