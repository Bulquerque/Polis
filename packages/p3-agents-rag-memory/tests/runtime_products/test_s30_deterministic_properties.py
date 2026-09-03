from __future__ import annotations

from copy import deepcopy

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M01_social_feature_builder import run_module as m1
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M02_context_memory_feature_builder import run_module as m2


def test_m01_evidence_order_does_not_change_output(s30_upstream_inputs, s30_execution_context, s30_projection_config):
    inputs = {k: s30_upstream_inputs[k] for k in (
        "validated_society_state_panel", "evidence_tag_panel", "agent_disagreement_panel"
    )}
    cfg = {"execution_context": s30_execution_context, "feature_projection_config": s30_projection_config}
    first = m1(inputs, cfg)["outputs"]["social_feature_panel"]
    changed = deepcopy(inputs)
    changed["evidence_tag_panel"]["records"].reverse()
    second = m1(changed, cfg)["outputs"]["social_feature_panel"]
    assert first == second


def test_m02_memory_order_does_not_change_output(s30_upstream_inputs, s30_execution_context, s30_projection_config):
    inputs = {k: s30_upstream_inputs[k] for k in (
        "next_memory_state", "validated_society_state_panel", "evidence_tag_panel"
    )}
    cfg = {"execution_context": s30_execution_context, "feature_projection_config": s30_projection_config}
    first = m2(inputs, cfg)["outputs"]["context_memory_feature_panel"]
    changed = deepcopy(inputs)
    changed["next_memory_state"]["records"].reverse()
    second = m2(changed, cfg)["outputs"]["context_memory_feature_panel"]
    assert first == second
