from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.models import (
    OptionsViewBinding,
    ViewReadinessReport,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.qualification import (
    MarketDerivativesQualificationBuilder,
)

MODULE_ID = "P3.S36.M04"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "option_contract_chain_handler_bundle_builder"
SUBPHASE = "P3.S36"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_LOCAL"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S36_M04_option_contract_chain_handler_bundle_builder.yaml"
REQUIRED_INPUTS = ("options_view_binding", "options_view_readiness_report")
PRODUCED_OUTPUTS = (
    "options_chain_handler_bundle",
    "options_chain_operation_qualification",
)


async def execute(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    binding = OptionsViewBinding.model_validate(inputs["options_view_binding"], strict=False)
    readiness = ViewReadinessReport.model_validate(
        inputs["options_view_readiness_report"], strict=False
    )
    bundle, qualification = MarketDerivativesQualificationBuilder().option_chain_bundle(
        binding=binding,
        readiness=readiness,
    )
    return {
        "options_chain_handler_bundle": bundle.model_dump(mode="json"),
        "options_chain_operation_qualification": qualification.model_dump(mode="json"),
    }
