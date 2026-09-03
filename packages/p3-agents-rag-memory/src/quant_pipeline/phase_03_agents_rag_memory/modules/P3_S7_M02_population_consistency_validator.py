from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.population.s7.models import PopulationValidationRequest
from ..foundation.population.s7.validator import PopulationConsistencyValidator

MODULE_ID = "P3.S7.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "population_consistency_validator"
SUBPHASE = "P3.S7"
from ._input_builders import model_from_declared_inputs

IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


@deprecated_legacy_entrypoint("P3.S7.M02")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a frozen population without silently rebalancing it."""
    del config
    request = model_from_declared_inputs(PopulationValidationRequest, inputs)
    result = PopulationConsistencyValidator().execute(request)
    return {
        "validated_population_manifest": (
            result.validated_population_manifest.model_dump(mode="json")
        )
    }

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
CONTRACT = 'modules/P3_S7_M02_population_consistency_validator.yaml'
REQUIRED_INPUTS = ('person_seed_panel', 'population_manifest', 'personality_coverage_report', 'population_representation_config', 'personality_creator_generation_audit')
PRODUCED_OUTPUTS = ('validated_population_manifest',)
