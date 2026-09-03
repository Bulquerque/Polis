from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.person_foundation.policy import (
    REQUIRED_INPUTS,
    load_person_schema_policy,
)

MODULE_ID = "P3.S4.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "person_schema_policy_loader"
PHASE = "phase_03_agents_rag_memory"
SUBPHASE = "P3.S4"
CONTRACT = "modules/P3_S4_M02_person_schema_policy_loader.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


@deprecated_legacy_entrypoint("P3.S4.M02")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load the canonical person schema and cross-registry policy."""
    output = load_person_schema_policy(inputs, config)
    return {
        "module_id": MODULE_ID,
        "module_name": MODULE_NAME,
        "phase": PHASE,
        "subphase": SUBPHASE,
        "contract": CONTRACT,
        "required_inputs": list(REQUIRED_INPUTS),
        "outputs": {"person_schema_policy": output},
        "implementation_status": IMPLEMENTATION_STATUS,
        "production_promotion_allowed": False,
    }

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
REQUIRED_INPUTS = ('person_schema_policy_config', 'personality_tag_registry', 'economic_role_taxonomy_config', 'role_objective_registry_config', 'population_representation_config')
PRODUCED_OUTPUTS = ('person_schema_policy',)
