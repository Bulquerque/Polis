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

MODULE_ID = "P3.S36.M05"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "option_surface_diagnostic_handler_bundle_builder"
SUBPHASE = "P3.S36"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_LOCAL"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S36_M05_option_surface_diagnostic_handler_bundle_builder.yaml"
REQUIRED_INPUTS = ("options_view_binding", "options_view_readiness_report")
OPTIONAL_INPUTS = ("surface_capabilities",)
PRODUCED_OUTPUTS = (
    "options_surface_handler_bundle",
    "options_surface_operation_qualification",
)


async def execute(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    binding = OptionsViewBinding.model_validate(inputs["options_view_binding"], strict=False)
    readiness = ViewReadinessReport.model_validate(
        inputs["options_view_readiness_report"], strict=False
    )
    capabilities = inputs.get("surface_capabilities", {})
    sufficient = bool(
        isinstance(capabilities, Mapping)
        and capabilities.get("sufficient_surface_coverage", False)
    )
    bundle, qualification = MarketDerivativesQualificationBuilder().option_surface_bundle(
        binding=binding,
        readiness=readiness,
        sufficient_surface_coverage=sufficient,
    )
    return {
        "options_surface_handler_bundle": bundle.model_dump(mode="json"),
        "options_surface_operation_qualification": qualification.model_dump(mode="json"),
    }
