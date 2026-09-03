"""Canonical wrapper for P3.S32.M03."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from ..s32 import build_compatibility_overlay

MODULE_ID = "P3.S32.M03"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "legacy_tool_plane_compatibility_overlay_builder"
SUBPHASE = "P3.S32"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S32_M03_legacy_tool_plane_compatibility_overlay_builder.yaml"
REQUIRED_INPUTS = ('tool_registry', 'mcp_gateway_policy', 'provider_adapter_registry_config', 'canonical_research_tool_catalog', 'canonical_tool_operation_registry', 'compatibility_alias_config')
PRODUCED_OUTPUTS = ('extended_tool_registry_overlay', 'provider_transport_overlay', 'compatibility_alias_registry', 'legacy_contract_projection_report')
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    """Validate and build deterministic legacy tool plane compatibility overlay builder artifacts."""
    del context
    return build_compatibility_overlay(dict(inputs))
