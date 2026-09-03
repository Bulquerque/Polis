from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from quant_pipeline.phase_03_agents_rag_memory.s17.underlying_resolver import (
    resolve_external_stimulus_stream,
)

MODULE_ID = "P3.S17.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "canonical_underlying_resolver"
SUBPHASE = "P3.S17"
CONTRACT = "modules/P3_S17_M02_canonical_underlying_resolver.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
IMPLEMENTED = True
REQUIRED_INPUTS = [
    "external_stimulus_stream",
    "entity_underlying_map_config",
    "proposition_registry_config",
]
PRODUCED_OUTPUTS = ('resolved_external_stimulus_stream',)


@deprecated_legacy_entrypoint("P3.S17.M02")
def run_module(inputs: dict[str, object], config: dict[str, object] | None = None) -> dict[str, object]:
    """Resolve canonical underlyings without inventing identifiers."""

    del config
    return resolve_external_stimulus_stream(inputs).model_dump(mode="json")

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))

