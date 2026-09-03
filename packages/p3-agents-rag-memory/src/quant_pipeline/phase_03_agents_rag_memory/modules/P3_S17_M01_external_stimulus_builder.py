from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from quant_pipeline.phase_03_agents_rag_memory.s17.stimulus_builder import (
    build_external_stimulus_stream,
)

MODULE_ID = "P3.S17.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "external_stimulus_builder"
SUBPHASE = "P3.S17"
CONTRACT = "modules/P3_S17_M01_external_stimulus_builder.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
IMPLEMENTED = True
REQUIRED_INPUTS = [
    "pit_validated_context",
    "graph_rag_artifact",
    "phase3_run_snapshot",
    "stimulus_bus_config",
]
PRODUCED_OUTPUTS = ('external_stimulus_stream',)


@deprecated_legacy_entrypoint("P3.S17.M01")
def run_module(inputs: dict[str, object], config: dict[str, object] | None = None) -> dict[str, object]:
    """Build a PIT-safe external stimulus stream; raises a typed error on failure."""

    del config
    return build_external_stimulus_stream(inputs).model_dump(mode="json")

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))

