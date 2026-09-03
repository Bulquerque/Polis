"""Canonical wrapper for P3.S34.M02."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from ..s34 import build_person_research_profiles

MODULE_ID = "P3.S34.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "person_research_capability_profiler"
SUBPHASE = "P3.S34"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S34_M02_person_research_capability_profiler.yaml"
REQUIRED_INPUTS = ('person_seed_panel', 'validated_population_manifest', 'person_schema_policy', 'research_capability_taxonomy', 'capability_profile_policy_config', 'phase3_run_snapshot')
OPTIONAL_INPUTS = ()
PRODUCED_OUTPUTS = ('person_research_capability_panel', 'person_research_resource_panel', 'capability_profile_coverage_report')
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    """Execute the deterministic P3.S34 builder."""
    del context
    return build_person_research_profiles(dict(inputs))
