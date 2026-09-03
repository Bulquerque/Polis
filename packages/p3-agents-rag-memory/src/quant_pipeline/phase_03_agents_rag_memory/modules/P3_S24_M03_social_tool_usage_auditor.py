from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from ..runtime.social_delivery import audit_social_tool_usage
from ..runtime_shared.s21_models import PersonToolEntitlementPanel, ValidatedToolCallRequestPanel
from ..runtime_shared.s24_models import SocialDeliveryPanel, SocialToolAuditPolicy
from ._s24_wrapper import parse_model, parse_optional_config

MODULE_ID = "P3.S24.M03"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "social_tool_usage_auditor"
SUBPHASE = "P3.S24"
CONTRACT = "modules/P3_S24_M03_social_tool_usage_auditor.yaml"
REQUIRED_INPUTS = [
    "social_delivery_panel",
    "validated_tool_call_request_panel",
    "person_tool_entitlement_panel",
]
PRODUCED_OUTPUTS = ('social_tool_audit_panel',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S24.M03")
def run_module(inputs: Mapping[str, object], config: Mapping[str, object] | None = None) -> dict[str, object]:
    policy = parse_optional_config(
        config,
        "social_tool_audit_policy",
        SocialToolAuditPolicy,
        module_id=MODULE_ID,
        default=SocialToolAuditPolicy(),
    )
    output = audit_social_tool_usage(
        deliveries=parse_model(inputs, "social_delivery_panel", SocialDeliveryPanel, module_id=MODULE_ID),
        requests=parse_model(inputs, "validated_tool_call_request_panel", ValidatedToolCallRequestPanel, module_id=MODULE_ID),
        entitlements=parse_model(inputs, "person_tool_entitlement_panel", PersonToolEntitlementPanel, module_id=MODULE_ID),
        policy=policy,
    )
    return {"social_tool_audit_panel": output.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
