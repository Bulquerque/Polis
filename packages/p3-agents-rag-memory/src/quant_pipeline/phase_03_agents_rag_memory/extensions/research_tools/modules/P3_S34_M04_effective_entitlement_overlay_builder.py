"""Canonical wrapper for P3.S34.M04."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from ..s34 import build_effective_entitlements

MODULE_ID = "P3.S34.M04"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "effective_entitlement_overlay_builder"
SUBPHASE = "P3.S34"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S34_M04_effective_entitlement_overlay_builder.yaml"
REQUIRED_INPUTS = ('person_tool_entitlement_panel', 'person_research_capability_panel', 'person_research_resource_panel', 'canonical_tool_operation_registry', 'research_mode_registry', 'research_plan_registry', 'phase2_research_view_readiness_report', 'provider_transport_overlay', 'research_entitlement_policy_config', 'mcp_gateway_policy', 'phase3_run_snapshot')
OPTIONAL_INPUTS = ()
PRODUCED_OUTPUTS = ('extended_person_tool_entitlement_panel', 'entitlement_resolution_audit')
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    """Execute the deterministic P3.S34 builder."""
    del context
    return build_effective_entitlements(dict(inputs))
