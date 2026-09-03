from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.models import (
    MarketViewBinding,
    ViewReadinessReport,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.qualification import (
    MarketDerivativesQualificationBuilder,
)

MODULE_ID = "P3.S36.M03"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "corporate_action_cross_asset_handler_bundle_builder"
SUBPHASE = "P3.S36"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_LOCAL"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S36_M03_corporate_action_cross_asset_handler_bundle_builder.yaml"
REQUIRED_INPUTS = ("market_view_binding", "market_view_readiness_report")
PRODUCED_OUTPUTS = (
    "market_structural_handler_bundle",
    "market_structural_operation_qualification",
)


async def execute(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    binding = MarketViewBinding.model_validate(inputs["market_view_binding"], strict=False)
    readiness = ViewReadinessReport.model_validate(
        inputs["market_view_readiness_report"], strict=False
    )
    bundle, qualification = MarketDerivativesQualificationBuilder().market_structural_bundle(
        binding=binding,
        readiness=readiness,
    )
    return {
        "market_structural_handler_bundle": bundle.model_dump(mode="json"),
        "market_structural_operation_qualification": qualification.model_dump(mode="json"),
    }
