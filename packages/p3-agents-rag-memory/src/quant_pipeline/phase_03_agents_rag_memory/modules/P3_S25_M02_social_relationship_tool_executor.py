from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping
from typing import Any

from ..s25.entrypoints import prepare_inputs, run_guarded
from ..s25.relationships import evaluate_relationship_candidates

MODULE_ID = "P3.S25.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "social_relationship_tool_executor"
SUBPHASE = "P3.S25"
CONTRACT = "modules/P3_S25_M02_social_relationship_tool_executor.yaml"
IMPLEMENTED = True
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = (
    "updated_social_graph",
    "social_tool_audit_panel",
    "active_retro_policy_patch",
    "relationship_formation_config",
)
PRODUCED_OUTPUTS = ('relationship_candidate_panel',)


@deprecated_legacy_entrypoint("P3.S25.M02")
def run_module(
    inputs: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate plausible new relationships without mutating the graph."""
    materialized = prepare_inputs(
        module_id=MODULE_ID,
        inputs=inputs,
        required=REQUIRED_INPUTS,
        config_key="relationship_formation_config",
        config=config,
    )
    return run_guarded(
        MODULE_ID,
        lambda: {
            "relationship_candidate_panel": evaluate_relationship_candidates(
                **materialized
            ).model_dump(mode="json")
        },
    )

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))

