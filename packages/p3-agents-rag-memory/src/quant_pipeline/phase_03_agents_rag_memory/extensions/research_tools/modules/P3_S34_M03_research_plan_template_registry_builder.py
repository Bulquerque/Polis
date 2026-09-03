"""Canonical wrapper for P3.S34.M03."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from ..s34 import build_research_plan_templates

MODULE_ID = "P3.S34.M03"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "research_plan_template_registry_builder"
SUBPHASE = "P3.S34"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S34_M03_research_plan_template_registry_builder.yaml"
REQUIRED_INPUTS = ('research_plan_registry_config', 'canonical_tool_operation_registry', 'research_mode_registry', 'research_capability_taxonomy', 'phase2_research_view_readiness_report')
OPTIONAL_INPUTS = ()
PRODUCED_OUTPUTS = ('research_plan_registry', 'research_plan_dependency_matrix', 'research_plan_readiness_report')
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    """Execute the deterministic P3.S34 builder."""
    del context
    return build_research_plan_templates(dict(inputs))
