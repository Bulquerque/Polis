from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.population.s7.builder import FixedPopulationBuilder
from ..foundation.population.s7.models import FixedPopulationBuildRequest

MODULE_ID = "P3.S7.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "fixed_population_builder"
SUBPHASE = "P3.S7"
from ._input_builders import model_from_declared_inputs

IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


@deprecated_legacy_entrypoint("P3.S7.M01")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze stable identities, weights and provenance for the population."""
    del config
    request = model_from_declared_inputs(FixedPopulationBuildRequest, inputs)
    result = FixedPopulationBuilder().execute(request)
    return {
        "person_seed_panel": result.person_seed_panel.model_dump(mode="json"),
        "population_manifest": result.population_manifest.model_dump(mode="json"),
    }

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
CONTRACT = 'modules/P3_S7_M01_fixed_population_builder.yaml'
REQUIRED_INPUTS = ('finalized_personality_candidate_pool', 'population_generation_control', 'person_schema_policy', 'population_representation_config')
PRODUCED_OUTPUTS = ('person_seed_panel', 'population_manifest')
