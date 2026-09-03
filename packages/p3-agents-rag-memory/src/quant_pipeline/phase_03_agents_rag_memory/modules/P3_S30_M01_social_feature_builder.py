from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..s30_products import build_social_features

MODULE_ID = "P3.S30.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "social_feature_builder"
SUBPHASE = "P3.S30"
CONTRACT = "modules/P3_S30_M01_social_feature_builder.yaml"
REQUIRED_INPUTS = (
    "validated_society_state_panel",
    "evidence_tag_panel",
    "agent_disagreement_panel",
)
PRODUCED_OUTPUTS = ('social_feature_panel',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S30.M01")
def run_module(inputs: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    context = config.get("execution_context")
    if not isinstance(context, dict):
        raise ValueError("P3.S30.M01 requires an explicit deterministic execution context")
    projection = config.get("feature_projection_config")
    if not isinstance(projection, dict):
        raise ValueError("P3.S30.M01 requires feature_projection_config in config")
    payload = dict(inputs)
    payload["feature_projection_config"] = projection
    return build_social_features(payload, context)

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
