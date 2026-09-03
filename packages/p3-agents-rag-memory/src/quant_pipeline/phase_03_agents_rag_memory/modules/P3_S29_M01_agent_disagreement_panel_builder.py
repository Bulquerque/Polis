from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping
from typing import Any

from ..s29_products import build_agent_disagreement_panel

MODULE_ID = "P3.S29.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "agent_disagreement_panel_builder"
SUBPHASE = "P3.S29"
CONTRACT = "modules/P3_S29_M01_agent_disagreement_panel_builder.yaml"
REQUIRED_INPUTS = [
    "belief_distribution_panel",
    "validated_society_state_panel",
    "aggregation_semantics_config",
]
PRODUCED_OUTPUTS = ('agent_disagreement_panel',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S29.M01")
def run_module(
    inputs: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic disagreement panel from canonical aggregate inputs."""

    if config is None:
        raise ValueError("P3.S29.M01 requires an explicit deterministic execution context")
    return build_agent_disagreement_panel(inputs, config)

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
