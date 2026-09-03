from __future__ import annotations
from .test_p3_s3_m01_promoted_retro_update_ingestor import _inputs as retro_inputs
from .test_p3_s3_m02_matured_belief_feedback_ingestor import _inputs as feedback_inputs
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S3_M01_promoted_retro_update_ingestor import run_module as retro
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S3_M02_matured_belief_feedback_ingestor import run_module as feedback


def test_empty_promoted_feedback_contracts_are_explicit(root, governance_outputs):
    ctx={"current_cycle_id":2,"processed_at":"2026-07-27T12:00:00Z","package_root":root}
    a=retro(retro_inputs(root,governance_outputs),ctx)["outputs"]["active_retro_policy_patch"]
    b=feedback(feedback_inputs(governance_outputs),ctx)["outputs"]["active_belief_feedback_bundle"]
    assert a["status"]=="NO_PATCH" and a["patch"] is None
    assert b["status"]=="NO_MATURED_FEEDBACK" and b["feedback_items"]==[]
