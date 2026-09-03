"""Canonical wrapper for P3.S34.M01."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from ..s34 import build_capability_taxonomy_contracts

MODULE_ID = "P3.S34.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "research_capability_taxonomy_builder"
SUBPHASE = "P3.S34"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S34_M01_research_capability_taxonomy_builder.yaml"
REQUIRED_INPUTS = ('research_capability_taxonomy_config', 'canonical_research_tool_catalog', 'canonical_tool_operation_registry', 'research_mode_registry', 'person_schema_policy')
OPTIONAL_INPUTS = ()
PRODUCED_OUTPUTS = ('research_capability_taxonomy', 'capability_operation_requirement_matrix')
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    """Execute the deterministic P3.S34 builder."""
    del context
    return build_capability_taxonomy_contracts(dict(inputs))
