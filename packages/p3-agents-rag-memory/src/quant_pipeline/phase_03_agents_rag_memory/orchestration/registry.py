"""Stable legacy authority plus the executable research-tools extension.

``MODULE_REGISTRY`` remains the immutable 81-module legacy authority.
``EXECUTABLE_MODULE_REGISTRY`` is the composed execution surface and adds the
47 S32-S40 research-tool modules without changing legacy consumers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModuleRegistration:
    """Stable binding between a contract module and its Python entrypoint."""

    module_id: str
    module_name: str
    subphase_id: str
    implementation_path: str


FOUNDATION_MODULE_REGISTRY: tuple[ModuleRegistration, ...] = (
    ModuleRegistration(
        module_id="P3.S1.M01",
        module_name="phase2_handoff_contract_validator",
        subphase_id="P3.S1",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S1_M01_phase2_handoff_contract_validator",
    ),
    ModuleRegistration(
        module_id="P3.S1.M02",
        module_name="source_quality_context_guard",
        subphase_id="P3.S1",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S1_M02_source_quality_context_guard",
    ),
    ModuleRegistration(
        module_id="P3.S2.M01",
        module_name="point_in_time_context_gate",
        subphase_id="P3.S2",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S2_M01_point_in_time_context_gate",
    ),
    ModuleRegistration(
        module_id="P3.S2.M02",
        module_name="phase3_run_snapshot_builder",
        subphase_id="P3.S2",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S2_M02_phase3_run_snapshot_builder",
    ),
    ModuleRegistration(
        module_id="P3.S2.M03",
        module_name="model_knowledge_cutoff_firewall",
        subphase_id="P3.S2",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S2_M03_model_knowledge_cutoff_firewall",
    ),
    ModuleRegistration(
        module_id="P3.S3.M01",
        module_name="promoted_retro_update_ingestor",
        subphase_id="P3.S3",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S3_M01_promoted_retro_update_ingestor",
    ),
    ModuleRegistration(
        module_id="P3.S3.M02",
        module_name="matured_belief_feedback_ingestor",
        subphase_id="P3.S3",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S3_M02_matured_belief_feedback_ingestor",
    ),
    ModuleRegistration(
        module_id="P3.S4.M01",
        module_name="personality_tag_registry_loader",
        subphase_id="P3.S4",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S4_M01_personality_tag_registry_loader",
    ),
    ModuleRegistration(
        module_id="P3.S4.M02",
        module_name="person_schema_policy_loader",
        subphase_id="P3.S4",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S4_M02_person_schema_policy_loader",
    ),
    ModuleRegistration(
        module_id="P3.S5.M01",
        module_name="personality_candidate_generator",
        subphase_id="P3.S5",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S5_M01_personality_candidate_generator",
    ),
    ModuleRegistration(
        module_id="P3.S5.M02",
        module_name="personality_candidate_consistency_checker",
        subphase_id="P3.S5",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S5_M02_personality_candidate_consistency_checker",
    ),
    ModuleRegistration(
        module_id="P3.S6.M01",
        module_name="personality_coverage_metric_calculator",
        subphase_id="P3.S6",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S6_M01_personality_coverage_metric_calculator",
    ),
    ModuleRegistration(
        module_id="P3.S6.M02",
        module_name="coverage_density_controller",
        subphase_id="P3.S6",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S6_M02_coverage_density_controller",
    ),
    ModuleRegistration(
        module_id="P3.S7.M01",
        module_name="fixed_population_builder",
        subphase_id="P3.S7",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S7_M01_fixed_population_builder",
    ),
    ModuleRegistration(
        module_id="P3.S7.M02",
        module_name="population_consistency_validator",
        subphase_id="P3.S7",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S7_M02_population_consistency_validator",
    ),
    ModuleRegistration(
        module_id="P3.S8.M01",
        module_name="initial_social_graph_builder",
        subphase_id="P3.S8",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S8_M01_initial_social_graph_builder",
    ),
    ModuleRegistration(
        module_id="P3.S8.M02",
        module_name="relationship_prior_validator",
        subphase_id="P3.S8",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S8_M02_relationship_prior_validator",
    ),
    ModuleRegistration(
        module_id="P3.S9.M01",
        module_name="warmup_history_validator",
        subphase_id="P3.S9",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S9_M01_warmup_history_validator",
    ),
    ModuleRegistration(
        module_id="P3.S10.M01",
        module_name="warmup_scheduler",
        subphase_id="P3.S10",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S10_M01_warmup_scheduler",
    ),
    ModuleRegistration(
        module_id="P3.S10.M02",
        module_name="warmup_checkpoint_planner",
        subphase_id="P3.S10",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S10_M02_warmup_checkpoint_planner",
    ),
    ModuleRegistration(
        module_id="P3.S11.M01",
        module_name="warmup_replay_orchestrator",
        subphase_id="P3.S11",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S11_M01_warmup_replay_orchestrator",
    ),
    ModuleRegistration(
        module_id="P3.S11.M02",
        module_name="bootstrap_leakage_guard",
        subphase_id="P3.S11",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S11_M02_bootstrap_leakage_guard",
    ),
    ModuleRegistration(
        module_id="P3.S11.M03",
        module_name="cycle_state_loader",
        subphase_id="P3.S11",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S11_M03_cycle_state_loader",
    ),
    ModuleRegistration(
        module_id="P3.S12.M01",
        module_name="document_chunker_and_indexer",
        subphase_id="P3.S12",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S12_M01_document_chunker_and_indexer",
    ),
    ModuleRegistration(
        module_id="P3.S12.M02",
        module_name="retrieval_index_manifest_builder",
        subphase_id="P3.S12",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S12_M02_retrieval_index_manifest_builder",
    ),
    ModuleRegistration(
        module_id="P3.S13.M01",
        module_name="temporal_graph_builder",
        subphase_id="P3.S13",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S13_M01_temporal_graph_builder",
    ),
    ModuleRegistration(
        module_id="P3.S13.M02",
        module_name="graph_evidence_linker",
        subphase_id="P3.S13",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S13_M02_graph_evidence_linker",
    ),
    ModuleRegistration(
        module_id="P3.S14.M01",
        module_name="memory_access_policy_builder",
        subphase_id="P3.S14",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S14_M01_memory_access_policy_builder",
    ),
    ModuleRegistration(
        module_id="P3.S14.M02",
        module_name="memory_index_manifest_builder",
        subphase_id="P3.S14",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S14_M02_memory_index_manifest_builder",
    ),
    ModuleRegistration(
        module_id="P3.S15.M01",
        module_name="tool_registry_builder",
        subphase_id="P3.S15",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S15_M01_tool_registry_builder",
    ),
    ModuleRegistration(
        module_id="P3.S15.M02",
        module_name="person_tool_entitlement_router",
        subphase_id="P3.S15",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S15_M02_person_tool_entitlement_router",
    ),
    ModuleRegistration(
        module_id="P3.S16.M01",
        module_name="mcp_tool_gateway_policy_builder",
        subphase_id="P3.S16",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S16_M01_mcp_tool_gateway_policy_builder",
    ),
    ModuleRegistration(
        module_id="P3.S16.M02",
        module_name="tool_call_audit_contract_builder",
        subphase_id="P3.S16",
        implementation_path="quant_pipeline.phase_03_agents_rag_memory.modules.P3_S16_M02_tool_call_audit_contract_builder",
    ),
)


from ..runtime_engine.execution.catalog import MODULE_IMPORT_PATHS


def _runtime_registration(module_id: str, implementation_path: str) -> ModuleRegistration:
    module_file = implementation_path.rsplit(".", 1)[-1]
    prefix = module_id.replace(".", "_") + "_"
    module_name = module_file[len(prefix):] if module_file.startswith(prefix) else module_file
    return ModuleRegistration(
        module_id=module_id,
        module_name=module_name,
        subphase_id=".".join(module_id.split(".")[:2]),
        implementation_path=implementation_path,
    )


RUNTIME_MODULE_REGISTRY: tuple[ModuleRegistration, ...] = tuple(
    _runtime_registration(module_id, path)
    for module_id, path in MODULE_IMPORT_PATHS.items()
)

LEGACY_MODULE_REGISTRY: tuple[ModuleRegistration, ...] = FOUNDATION_MODULE_REGISTRY + RUNTIME_MODULE_REGISTRY

if len(LEGACY_MODULE_REGISTRY) != 81 or len({item.module_id for item in LEGACY_MODULE_REGISTRY}) != 81:
    raise RuntimeError("P3 legacy module registry must contain 81 unique modules")

from .extension_authority import extension_module_rows


def _extension_registration(row: object) -> ModuleRegistration:
    if not isinstance(row, dict):
        row = dict(row)  # type: ignore[arg-type]
    implementation = str(row["implementation_path"])
    if implementation.startswith("src/"):
        implementation = implementation.removeprefix("src/").removesuffix(".py").replace("/", ".")
    return ModuleRegistration(
        module_id=str(row["module_id"]),
        module_name=str(row["module_name"]),
        subphase_id=str(row["subphase_id"]),
        implementation_path=implementation,
    )


RESEARCH_TOOLS_EXTENSION_MODULE_REGISTRY: tuple[ModuleRegistration, ...] = tuple(
    _extension_registration(row) for row in extension_module_rows()
)

MODULE_REGISTRY: tuple[ModuleRegistration, ...] = LEGACY_MODULE_REGISTRY

EXECUTABLE_MODULE_REGISTRY: tuple[ModuleRegistration, ...] = (
    MODULE_REGISTRY + RESEARCH_TOOLS_EXTENSION_MODULE_REGISTRY
)

if len(EXECUTABLE_MODULE_REGISTRY) != 128 or len({item.module_id for item in EXECUTABLE_MODULE_REGISTRY}) != 128:
    raise RuntimeError("P3 combined module registry must contain 128 unique modules")

_BY_ID = {registration.module_id: registration for registration in EXECUTABLE_MODULE_REGISTRY}


def by_id(module_id: str) -> ModuleRegistration:
    """Return one executable legacy or extension registration."""

    try:
        return _BY_ID[module_id]
    except KeyError as exc:
        raise KeyError(f"Unknown P3 module_id: {module_id}") from exc
