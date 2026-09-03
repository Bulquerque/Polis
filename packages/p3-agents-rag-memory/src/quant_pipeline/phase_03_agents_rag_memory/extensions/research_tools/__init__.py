"""Point-in-time research-tool extension contracts for Phase 3."""

from .s32 import (
    build_canonical_catalog,
    build_compatibility_overlay,
    build_extension_snapshot,
    build_mode_registry,
)
from .s33 import (
    build_entity_resolution_boundary,
    build_phase1_custody_boundary,
    build_phase2_view_boundary,
    build_research_data_boundary_bundle,
    build_temporal_firewall,
)
from .s34 import (
    build_capability_taxonomy_contracts,
    build_context_tool_overlay,
    build_effective_entitlements,
    build_person_research_profiles,
    build_research_plan_templates,
)

__all__ = [
    "build_canonical_catalog",
    "build_compatibility_overlay",
    "build_extension_snapshot",
    "build_mode_registry",
    "build_entity_resolution_boundary",
    "build_phase1_custody_boundary",
    "build_phase2_view_boundary",
    "build_research_data_boundary_bundle",
    "build_temporal_firewall",
    "build_capability_taxonomy_contracts",
    "build_context_tool_overlay",
    "build_effective_entitlements",
    "build_person_research_profiles",
    "build_research_plan_templates",
]
