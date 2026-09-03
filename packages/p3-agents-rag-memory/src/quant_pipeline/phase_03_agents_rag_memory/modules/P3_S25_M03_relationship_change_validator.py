from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping
from typing import Any

from ..s25.entrypoints import prepare_inputs, run_guarded
from ..s25.topology import validate_and_materialize_relationship_changes

MODULE_ID = "P3.S25.M03"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "relationship_change_validator"
SUBPHASE = "P3.S25"
CONTRACT = "modules/P3_S25_M03_relationship_change_validator.yaml"
IMPLEMENTED = True
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = (
    "updated_social_graph",
    "relationship_candidate_panel",
    "social_graph_config",
)
PRODUCED_OUTPUTS = ('next_social_graph',)


@deprecated_legacy_entrypoint("P3.S25.M03")
def run_module(
    inputs: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate eligible changes and materialize the next social graph."""
    materialized = prepare_inputs(
        module_id=MODULE_ID,
        inputs=inputs,
        required=REQUIRED_INPUTS,
        config_key="social_graph_config",
        config=config,
    )
    return run_guarded(
        MODULE_ID,
        lambda: {
            "next_social_graph": validate_and_materialize_relationship_changes(
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

