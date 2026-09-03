from __future__ import annotations

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M04_phase4_social_handoff_builder import run_module as m4
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M05_variable_evolution_handoff_builder import run_module as m5


def test_s30_end_to_end_handoff(s30_products, s30_execution_context, s30_upstream_inputs):
    handoff = m4({
        "social_feature_panel": s30_products["social_feature_panel"],
        "evidence_tag_panel": s30_upstream_inputs["evidence_tag_panel"],
        "agent_disagreement_panel": s30_upstream_inputs["agent_disagreement_panel"],
        "context_memory_feature_panel": s30_products["context_memory_feature_panel"],
        "hypothesis_registry": s30_products["hypothesis_registry"],
        "phase3_run_snapshot": s30_upstream_inputs["phase3_run_snapshot"],
    }, {"execution_context": s30_execution_context})["outputs"]["phase4_social_handoff_manifest"]
    variable = m5({
        "validated_society_state_panel": s30_upstream_inputs["validated_society_state_panel"],
        "social_feature_panel": s30_products["social_feature_panel"],
        "context_memory_feature_panel": s30_products["context_memory_feature_panel"],
        "hypothesis_registry": s30_products["hypothesis_registry"],
        "belief_outcome_commitment_log": s30_upstream_inputs["belief_outcome_commitment_log"],
        "phase3_run_snapshot": s30_upstream_inputs["phase3_run_snapshot"],
    }, {"execution_context": s30_execution_context})["outputs"]["variable_evolution_input_manifest"]
    assert handoff["complete"] is True
    assert handoff["expected_output_count"] == 6
    assert variable["social_feature_ref"] == s30_products["social_feature_panel"]["artifact_id"]
    assert variable["hypothesis_registry_ref"] == s30_products["hypothesis_registry"]["artifact_id"]


def test_s30_outputs_are_byte_stable(s30_products):
    import json
    first = json.dumps(s30_products, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    second = json.dumps(s30_products, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert first == second
