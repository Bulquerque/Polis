"""Canonical entrypoint for P3.S27.M01."""
from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext
from collections.abc import Mapping
from typing import Any
from quant_pipeline.phase_03_agents_rag_memory.s27.entrypoints import run_m01

MODULE_ID = "P3.S27.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "belief_distribution_aggregator"
SUBPHASE = "P3.S27"
CONTRACT = "modules/P3_S27_M01_belief_distribution_aggregator.yaml"
IMPLEMENTED = True
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = ('next_belief_state_panel', 'validated_population_manifest', 'stimulus_panel', 'proposition_registry_config', 'aggregation_semantics_config')
PRODUCED_OUTPUTS = ('belief_distribution_panel',)


@deprecated_legacy_entrypoint("P3.S27.M01")
def run_module(inputs: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return run_m01(inputs, config)

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))

