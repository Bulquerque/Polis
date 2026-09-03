"""Canonical wrapper for P3.S33.M04."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from ..s33 import build_entity_resolution_boundary

MODULE_ID = "P3.S33.M04"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "temporal_entity_instrument_resolver_builder"
SUBPHASE = "P3.S33"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S33_M04_temporal_entity_instrument_resolver_builder.yaml"
REQUIRED_INPUTS = ('entity_underlying_map_config', 'phase2_research_view_manifest', 'pit_visibility_policy')
OPTIONAL_INPUTS = ('clean_underlying_panel', 'clean_option_contract_panel', 'clean_document_panel', 'clean_event_reference_panel', 'clean_corporate_actions_panel')
PRODUCED_OUTPUTS = ('temporal_entity_resolution_index', 'entity_resolution_policy', 'entity_resolution_qualification_report')
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    """Build deterministic P3.S33 boundary artifacts."""
    del context
    return build_entity_resolution_boundary(dict(inputs))
