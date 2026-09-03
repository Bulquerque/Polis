"""Canonical wrapper for P3.S34.M05."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from ..s34 import build_context_tool_overlay

MODULE_ID = "P3.S34.M05"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "person_context_tool_descriptor_overlay_builder"
SUBPHASE = "P3.S34"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S34_M05_person_context_tool_descriptor_overlay_builder.yaml"
REQUIRED_INPUTS = ('validated_person_context_bundle', 'extended_person_tool_entitlement_panel', 'person_research_capability_panel', 'research_plan_registry', 'canonical_research_tool_catalog', 'canonical_tool_operation_registry', 'research_mode_registry', 'person_seed_panel', 'phase3_run_snapshot', 'cognition_config', 'context_tool_descriptor_policy_config')
OPTIONAL_INPUTS = ()
PRODUCED_OUTPUTS = ('extended_validated_person_context_bundle', 'context_projection_audit')
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    """Execute the deterministic P3.S34 builder."""
    del context
    return build_context_tool_overlay(dict(inputs))
