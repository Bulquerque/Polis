from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.resources.tool_registry.module_m02 import PersonToolEntitlementRouter
from ..foundation.resources.tool_registry.models import (
    PersonSchemaPolicy, PersonSeedPanel, ToolEntitlementConfig, ToolRegistryArtifact,
)
from ._runtime import require_service

MODULE_ID = "P3.S15.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "person_tool_entitlement_router"
SUBPHASE = "P3.S15"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


@deprecated_legacy_entrypoint("P3.S15.M02")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Route tool entitlements from the frozen population and policy."""
    service = require_service(config, expected_type=PersonToolEntitlementRouter)
    result = service.run(
        tool_registry=ToolRegistryArtifact.model_validate(inputs["tool_registry"], strict=False),
        person_seed_panel=PersonSeedPanel.model_validate(inputs["person_seed_panel"], strict=False),
        person_schema_policy=PersonSchemaPolicy.model_validate(inputs["person_schema_policy"], strict=False),
        entitlement_config=ToolEntitlementConfig.model_validate(inputs["tool_entitlement_config"], strict=False),
    )
    return {"person_tool_entitlement_panel": result.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
CONTRACT = 'modules/P3_S15_M02_person_tool_entitlement_router.yaml'
REQUIRED_INPUTS = ('tool_registry', 'person_seed_panel', 'person_schema_policy', 'tool_entitlement_config')
PRODUCED_OUTPUTS = ('person_tool_entitlement_panel',)
