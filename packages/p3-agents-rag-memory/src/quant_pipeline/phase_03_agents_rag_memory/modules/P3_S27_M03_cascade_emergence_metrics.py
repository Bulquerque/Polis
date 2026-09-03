"""Canonical entrypoint for P3.S27.M03."""
from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext
from collections.abc import Mapping
from typing import Any
from quant_pipeline.phase_03_agents_rag_memory.s27.entrypoints import run_m03

MODULE_ID = "P3.S27.M03"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "cascade_emergence_metrics"
SUBPHASE = "P3.S27"
CONTRACT = "modules/P3_S27_M03_cascade_emergence_metrics.yaml"
IMPLEMENTED = True
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = ('activation_panel', 'social_delivery_panel', 'social_tool_audit_panel', 'stimulus_panel', 'aggregation_semantics_config')
PRODUCED_OUTPUTS = ('cascade_metrics_panel',)


@deprecated_legacy_entrypoint("P3.S27.M03")
def run_module(inputs: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return run_m03(inputs, config)

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))

