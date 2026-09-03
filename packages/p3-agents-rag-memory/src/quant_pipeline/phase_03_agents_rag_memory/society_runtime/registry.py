"""Explicit registry for the twelve implemented society modules."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Final


@dataclass(frozen=True, slots=True)
class SocietyModuleDescriptor:
    module_id: str
    subphase: str
    module_name: str
    import_path: str


SOCIETY_SUBPHASES: Final[tuple[str, ...]] = ("P3.S25", "P3.S26", "P3.S27", "P3.S28")
SOCIETY_MODULES: Final[tuple[SocietyModuleDescriptor, ...]] = (
    SocietyModuleDescriptor("P3.S25.M01", "P3.S25", "trust_relationship_updater", "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S25_M01_trust_relationship_updater"),
    SocietyModuleDescriptor("P3.S25.M02", "P3.S25", "social_relationship_tool_executor", "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S25_M02_social_relationship_tool_executor"),
    SocietyModuleDescriptor("P3.S25.M03", "P3.S25", "relationship_change_validator", "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S25_M03_relationship_change_validator"),
    SocietyModuleDescriptor("P3.S26.M01", "P3.S26", "memory_consolidation_manager", "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S26_M01_memory_consolidation_manager"),
    SocietyModuleDescriptor("P3.S26.M02", "P3.S26", "endogenous_stimulus_queue_checkpoint_writer", "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S26_M02_endogenous_stimulus_queue_checkpoint_writer"),
    SocietyModuleDescriptor("P3.S26.M03", "P3.S26", "cycle_state_checkpoint_writer", "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S26_M03_cycle_state_checkpoint_writer"),
    SocietyModuleDescriptor("P3.S27.M01", "P3.S27", "belief_distribution_aggregator", "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S27_M01_belief_distribution_aggregator"),
    SocietyModuleDescriptor("P3.S27.M02", "P3.S27", "attention_information_asymmetry_metrics", "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S27_M02_attention_information_asymmetry_metrics"),
    SocietyModuleDescriptor("P3.S27.M03", "P3.S27", "cascade_emergence_metrics", "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S27_M03_cascade_emergence_metrics"),
    SocietyModuleDescriptor("P3.S28.M01", "P3.S28", "tag_conditioned_projection_engine", "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S28_M01_tag_conditioned_projection_engine"),
    SocietyModuleDescriptor("P3.S28.M02", "P3.S28", "underlying_society_state_vector_builder", "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S28_M02_underlying_society_state_vector_builder"),
    SocietyModuleDescriptor("P3.S28.M03", "P3.S28", "society_vector_quality_guard", "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S28_M03_society_vector_quality_guard"),
)


def society_status() -> dict[str, object]:
    """Return the material implementation status without executing business logic."""
    implemented: list[str] = []
    invalid: list[str] = []
    for descriptor in SOCIETY_MODULES:
        module = import_module(descriptor.import_path)
        if bool(getattr(module, "IMPLEMENTED", False)) and callable(getattr(module, "run_module", None)):
            implemented.append(descriptor.module_id)
        else:
            invalid.append(descriptor.module_id)
    return {
        "capability_id": "P3.RUNTIME.SOCIETY",
        "subphases": list(SOCIETY_SUBPHASES),
        "module_count": len(SOCIETY_MODULES),
        "implemented_count": len(implemented),
        "implemented_module_ids": implemented,
        "invalid_module_ids": invalid,
        "status": "IMPLEMENTED_QUALIFIED_INTERNAL" if not invalid else "INVALID",
        "production_promotion_allowed": False,
    }
