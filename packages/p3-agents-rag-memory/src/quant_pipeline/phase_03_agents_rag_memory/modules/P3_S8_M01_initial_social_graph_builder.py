from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.population.s8.builder import InitialSocialGraphBuilder
from ..foundation.population.s8.models import InitialSocialGraphBuildRequest

MODULE_ID = "P3.S8.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "initial_social_graph_builder"
SUBPHASE = "P3.S8"
from ._input_builders import model_from_declared_inputs

IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


@deprecated_legacy_entrypoint("P3.S8.M01")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the deterministic initial social graph."""
    del config
    missing = [name for name in REQUIRED_INPUTS if name not in inputs]
    if missing:
        raise ValueError(f"P3.S8.M01 missing inputs: {missing}")
    tag_registry = inputs.get("personality_tag_registry")
    if isinstance(tag_registry, dict):
        tag_registry = tuple(
            tag["tag_id"]
            for category in tag_registry.get("categories", ())
            for tag in category.get("tags", ())
        )
    request = model_from_declared_inputs(
        InitialSocialGraphBuildRequest,
        inputs,
        injected={"personality_tag_registry": tag_registry},
    )
    result = InitialSocialGraphBuilder().execute(request)
    return {"initial_social_graph": result.initial_social_graph.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
CONTRACT = 'modules/P3_S8_M01_initial_social_graph_builder.yaml'
REQUIRED_INPUTS = ('validated_population_manifest', 'person_seed_panel', 'social_graph_config', 'personality_tag_registry')
PRODUCED_OUTPUTS = ('initial_social_graph',)
