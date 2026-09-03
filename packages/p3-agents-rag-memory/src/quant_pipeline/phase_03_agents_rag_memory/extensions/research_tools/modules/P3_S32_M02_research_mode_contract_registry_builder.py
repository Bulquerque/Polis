"""Canonical wrapper for P3.S32.M02."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from ..s32 import build_mode_registry

MODULE_ID = "P3.S32.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "research_mode_contract_registry_builder"
SUBPHASE = "P3.S32"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S32_M02_research_mode_contract_registry_builder.yaml"
REQUIRED_INPUTS = ('canonical_tool_operation_registry', 'operation_mode_registry_config', 'research_capability_taxonomy_config')
PRODUCED_OUTPUTS = ('research_mode_registry', 'operation_mode_matrix')
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    """Validate and build deterministic research mode contract registry builder artifacts."""
    del context
    return build_mode_registry(dict(inputs))
