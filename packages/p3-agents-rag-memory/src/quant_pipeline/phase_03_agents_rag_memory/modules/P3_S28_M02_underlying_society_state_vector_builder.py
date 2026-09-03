"""P3.S28 module wrapper."""
from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext
from collections.abc import Mapping
from typing import Any
from ..s28.entrypoints import run_m02

MODULE_ID = 'P3.S28.M02'
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = 'underlying_society_state_vector_builder'
SUBPHASE = 'P3.S28'
CONTRACT = 'modules/P3_S28_M02_underlying_society_state_vector_builder.yaml'
REQUIRED_INPUTS = ['belief_distribution_panel', 'attention_information_metrics', 'cascade_metrics_panel', 'tag_projection_panel', 'emergence_vector_config', 'aggregation_semantics_config']
PRODUCED_OUTPUTS = ('synthetic_society_state_panel',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S28.M02")
def run_module(inputs: Mapping[str, object], config: Mapping[str, object] | None = None) -> dict[str, Any]:
    return run_m02(inputs, config)

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
