from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from quant_pipeline.phase_03_agents_rag_memory.s18.queue_loader import (
    load_endogenous_stimulus_queue,
)

MODULE_ID = "P3.S18.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "endogenous_stimulus_queue_loader"
SUBPHASE = "P3.S18"
CONTRACT = "modules/P3_S18_M01_endogenous_stimulus_queue_loader.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
IMPLEMENTED = True
REQUIRED_INPUTS = [
    "prior_cycle_endogenous_stimulus_queue",
    "phase3_run_snapshot",
    "stimulus_bus_config",
]
PRODUCED_OUTPUTS = ('endogenous_stimulus_stream',)


@deprecated_legacy_entrypoint("P3.S18.M01")
def run_module(
    inputs: dict[str, object],
    config: dict[str, object] | None = None,
) -> dict[str, object]:
    """Load only prior-cycle endogenous stimuli; fail closed on back-edges."""

    del config
    translated = dict(inputs)
    translated["stimulus_event_bus_config"] = translated.pop("stimulus_bus_config")
    return load_endogenous_stimulus_queue(translated).model_dump(mode="json")

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))

