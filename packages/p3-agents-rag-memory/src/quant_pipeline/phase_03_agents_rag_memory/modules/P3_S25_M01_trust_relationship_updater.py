from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping
from typing import Any

from ..s25.entrypoints import prepare_inputs, run_guarded
from ..s25.relationships import update_trust_relationships

MODULE_ID = "P3.S25.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "trust_relationship_updater"
SUBPHASE = "P3.S25"
CONTRACT = "modules/P3_S25_M01_trust_relationship_updater.yaml"
IMPLEMENTED = True
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = (
    "current_social_graph",
    "social_delivery_panel",
    "validated_next_person_state_panel",
    "active_belief_feedback_bundle",
    "relationship_update_config",
)
PRODUCED_OUTPUTS = ('updated_social_graph',)


@deprecated_legacy_entrypoint("P3.S25.M01")
def run_module(
    inputs: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Update trust on existing social edges without creating new edges."""
    materialized = prepare_inputs(
        module_id=MODULE_ID,
        inputs=inputs,
        required=REQUIRED_INPUTS,
        config_key="relationship_update_config",
        config=config,
    )
    return run_guarded(
        MODULE_ID,
        lambda: {
            "updated_social_graph": update_trust_relationships(**materialized).model_dump(
                mode="json"
            )
        },
    )

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))

