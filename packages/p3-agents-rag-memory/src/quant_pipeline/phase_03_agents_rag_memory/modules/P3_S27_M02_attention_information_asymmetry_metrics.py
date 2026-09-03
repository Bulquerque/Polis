"""Canonical entrypoint for P3.S27.M02."""
from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext
from collections.abc import Mapping
from typing import Any
from quant_pipeline.phase_03_agents_rag_memory.s27.entrypoints import run_m02

MODULE_ID = "P3.S27.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "attention_information_asymmetry_metrics"
SUBPHASE = "P3.S27"
CONTRACT = "modules/P3_S27_M02_attention_information_asymmetry_metrics.yaml"
IMPLEMENTED = True
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = ('validated_next_person_state_panel', 'tool_call_audit_panel', 'person_tool_entitlement_panel', 'validated_population_manifest', 'aggregation_semantics_config')
PRODUCED_OUTPUTS = ('attention_information_metrics',)


@deprecated_legacy_entrypoint("P3.S27.M02")
def run_module(inputs: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return run_m02(inputs, config)

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))

