"""Canonical entrypoint for P3.S39.M01."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.assembly import execute_m01

MODULE_ID = "P3.S39.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "return_risk_volatility_handler_bundle_builder"
SUBPHASE = "P3.S39"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S39_M01_return_risk_volatility_handler_bundle_builder.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = (
    "research_data_boundary_bundle",
    "quant_method_policy_config",
    "frequency_annualization_registry",
    "tool_operation_registry",
    "research_mode_registry",
)
PRODUCED_OUTPUTS = (
    "return_risk_volatility_handler_bundle",
    "return_volatility_method_manifest",
)


async def execute(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    return execute_m01(inputs, context)
