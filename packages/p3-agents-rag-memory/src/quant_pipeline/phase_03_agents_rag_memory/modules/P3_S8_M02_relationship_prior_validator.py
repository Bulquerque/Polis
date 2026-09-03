from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.population.s8.models import RelationshipPriorValidationRequest
from ..foundation.population.s8.validator import RelationshipPriorValidator

MODULE_ID = "P3.S8.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "relationship_prior_validator"
SUBPHASE = "P3.S8"
from ._input_builders import model_from_declared_inputs

IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


@deprecated_legacy_entrypoint("P3.S8.M02")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate relationship priors without creating replacement edges."""
    del config
    request = model_from_declared_inputs(RelationshipPriorValidationRequest, inputs)
    result = RelationshipPriorValidator().execute(request)
    return {
        "validated_initial_social_graph": (
            result.validated_initial_social_graph.model_dump(mode="json")
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
CONTRACT = 'modules/P3_S8_M02_relationship_prior_validator.yaml'
REQUIRED_INPUTS = ('initial_social_graph', 'social_graph_config')
PRODUCED_OUTPUTS = ('validated_initial_social_graph',)
