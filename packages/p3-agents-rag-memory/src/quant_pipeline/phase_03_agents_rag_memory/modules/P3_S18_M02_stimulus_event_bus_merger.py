from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from quant_pipeline.phase_03_agents_rag_memory.s18.event_bus import merge_stimulus_event_bus

MODULE_ID = "P3.S18.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "stimulus_event_bus_merger"
SUBPHASE = "P3.S18"
CONTRACT = "modules/P3_S18_M02_stimulus_event_bus_merger.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
IMPLEMENTED = True
REQUIRED_INPUTS = [
    "resolved_external_stimulus_stream",
    "endogenous_stimulus_stream",
    "stimulus_bus_config",
]
PRODUCED_OUTPUTS = ('stimulus_panel',)


@deprecated_legacy_entrypoint("P3.S18.M02")
def run_module(
    inputs: dict[str, object],
    config: dict[str, object] | None = None,
) -> dict[str, object]:
    """Merge stimuli deterministically, preserving origin, lineage and admission decisions."""

    del config
    translated = dict(inputs)
    translated["stimulus_event_bus_config"] = translated.pop("stimulus_bus_config")
    return merge_stimulus_event_bus(translated).model_dump(mode="json")

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))

