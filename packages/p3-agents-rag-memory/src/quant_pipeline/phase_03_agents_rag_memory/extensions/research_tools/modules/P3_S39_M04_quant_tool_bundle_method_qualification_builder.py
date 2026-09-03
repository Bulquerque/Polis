"""Canonical entrypoint for P3.S39.M04."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.assembly import execute_m04

MODULE_ID = "P3.S39.M04"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "quant_tool_bundle_method_qualification_builder"
SUBPHASE = "P3.S39"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S39_M04_quant_tool_bundle_method_qualification_builder.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = (
    "return_risk_volatility_handler_bundle",
    "dependence_entropy_handler_bundle",
    "event_window_scenario_handler_bundle",
    "quant_contract_test_report",
    "quant_property_test_report",
    "quant_leakage_test_report",
)
PRODUCED_OUTPUTS = (
    "quant_tool_handler_bundle",
    "quant_operation_mode_qualification",
    "quant_qualification_evidence_package",
)


async def execute(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    return execute_m04(inputs, context)
