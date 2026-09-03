"""Canonical entrypoint for P3.S39.M02."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.assembly import execute_m02

MODULE_ID = "P3.S39.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "dependence_entropy_handler_bundle_builder"
SUBPHASE = "P3.S39"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S39_M02_dependence_entropy_handler_bundle_builder.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = (
    "research_data_boundary_bundle",
    "dependence_method_policy_config",
    "entropy_discretization_registry",
    "tool_operation_registry",
    "research_mode_registry",
)
PRODUCED_OUTPUTS = (
    "dependence_entropy_handler_bundle",
    "dependence_entropy_method_manifest",
)


async def execute(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    return execute_m02(inputs, context)
