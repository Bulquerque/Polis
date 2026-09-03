from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.population.s5.consistency import (
    PersonalityCandidateConsistencyChecker,
)
from ..foundation.population.s5.models import ValidationRequest

MODULE_ID = "P3.S5.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "personality_candidate_consistency_checker"
SUBPHASE = "P3.S5"
from ._input_builders import model_from_declared_inputs

IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


@deprecated_legacy_entrypoint("P3.S5.M02")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply deterministic consistency rules to generated candidates."""
    del config
    request = model_from_declared_inputs(
        ValidationRequest,
        inputs,
        aliases={"consistency_rules_config": "personality_consistency_rules_config"},
    )
    result = PersonalityCandidateConsistencyChecker().execute(request)
    return {
        "validated_personality_candidate_pool": result.model_dump(mode="json")
    }

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
CONTRACT = 'modules/P3_S5_M02_personality_candidate_consistency_checker.yaml'
REQUIRED_INPUTS = ('personality_candidate_pool', 'person_schema_policy', 'personality_consistency_rules_config')
PRODUCED_OUTPUTS = ('validated_personality_candidate_pool',)
