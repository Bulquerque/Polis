"""P3.S28 module wrapper."""
from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext
from collections.abc import Mapping
from typing import Any
from ..s28.entrypoints import run_m01

MODULE_ID = 'P3.S28.M01'
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = 'tag_conditioned_projection_engine'
SUBPHASE = 'P3.S28'
CONTRACT = 'modules/P3_S28_M01_tag_conditioned_projection_engine.yaml'
REQUIRED_INPUTS = ['next_belief_state_panel', 'person_seed_panel', 'validated_population_manifest', 'validated_next_person_state_panel', 'personality_tag_registry', 'proposition_registry_config', 'aggregation_semantics_config']
PRODUCED_OUTPUTS = ('tag_projection_panel',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S28.M01")
def run_module(inputs: Mapping[str, object], config: Mapping[str, object] | None = None) -> dict[str, Any]:
    return run_m01(inputs, config)

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
