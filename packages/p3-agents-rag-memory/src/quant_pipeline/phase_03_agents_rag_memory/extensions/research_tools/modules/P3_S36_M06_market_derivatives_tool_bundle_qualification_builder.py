from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.models import (
    HandlerBundleManifest,
    OperationModeQualificationPanel,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.qualification import (
    MarketDerivativesQualificationBuilder,
)

MODULE_ID = "P3.S36.M06"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "market_derivatives_tool_bundle_qualification_builder"
SUBPHASE = "P3.S36"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_LOCAL"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S36_M06_market_derivatives_tool_bundle_qualification_builder.yaml"
REQUIRED_INPUTS = (
    "market_observation_handler_bundle",
    "market_structural_handler_bundle",
    "options_chain_handler_bundle",
    "options_surface_handler_bundle",
    "market_observation_operation_qualification",
    "market_structural_operation_qualification",
    "options_chain_operation_qualification",
    "options_surface_operation_qualification",
)
PRODUCED_OUTPUTS = (
    "market_tool_handler_bundle",
    "options_tool_handler_bundle",
    "market_derivatives_operation_mode_qualification",
    "market_derivatives_tool_readiness_report",
)


async def execute(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    bundles = tuple(
        HandlerBundleManifest.model_validate(inputs[name], strict=False)
        for name in (
            "market_observation_handler_bundle",
            "market_structural_handler_bundle",
            "options_chain_handler_bundle",
            "options_surface_handler_bundle",
        )
    )
    panels = tuple(
        OperationModeQualificationPanel.model_validate(inputs[name], strict=False)
        for name in (
            "market_observation_operation_qualification",
            "market_structural_operation_qualification",
            "options_chain_operation_qualification",
            "options_surface_operation_qualification",
        )
    )
    snapshot_ids = {panel.snapshot_id for panel in panels}
    if len(snapshot_ids) != 1:
        raise ValueError("qualification panels must share one snapshot_id")
    market, options, qualification, report = MarketDerivativesQualificationBuilder().consolidate(
        snapshot_id=next(iter(snapshot_ids)),
        bundles=bundles,
        panels=panels,
    )
    return {
        "market_tool_handler_bundle": market.model_dump(mode="json"),
        "options_tool_handler_bundle": options.model_dump(mode="json"),
        "market_derivatives_operation_mode_qualification": qualification.model_dump(mode="json"),
        "market_derivatives_tool_readiness_report": report.model_dump(mode="json"),
    }
