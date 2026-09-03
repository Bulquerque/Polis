from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from ..runtime.social_delivery import schedule_social_delivery
from ..runtime_shared.s24_models import SocialDeliveryConfig, SocialMessagePanel
from ._s24_wrapper import parse_model

MODULE_ID = "P3.S24.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "social_delivery_scheduler"
SUBPHASE = "P3.S24"
CONTRACT = "modules/P3_S24_M02_social_delivery_scheduler.yaml"
REQUIRED_INPUTS = ["social_message_panel", "social_delivery_config"]
PRODUCED_OUTPUTS = ('social_delivery_panel', 'social_delivery_event_panel')
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S24.M02")
def run_module(inputs: Mapping[str, object], config: Mapping[str, object] | None = None) -> dict[str, object]:
    del config
    delivery, events = schedule_social_delivery(
        messages=parse_model(inputs, "social_message_panel", SocialMessagePanel, module_id=MODULE_ID),
        config=parse_model(inputs, "social_delivery_config", SocialDeliveryConfig, module_id=MODULE_ID),
    )
    return {
        "social_delivery_panel": delivery.model_dump(mode="json"),
        "social_delivery_event_panel": events.model_dump(mode="json"),
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
