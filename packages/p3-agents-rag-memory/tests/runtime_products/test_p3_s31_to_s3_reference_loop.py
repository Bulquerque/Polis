from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from quant_pipeline.phase_03_agents_rag_memory.integration import (
    ReferenceOutcome,
    build_s3_feedback_handoff,
)
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S3_M02_matured_belief_feedback_ingestor import (
    run_module as ingest_feedback,
)

from .s31_support import execution_context, m01_inputs, run_m01, run_m02


def test_s31_reference_consumer_returns_s3_compatible_feedback(root, governance_outputs):
    inputs = m01_inputs()
    inputs["belief_outcome_commitment_log"]["records"][0]["matures_at"] = (
        "2024-01-31T20:01:00Z"
    )
    context = execution_context()
    bundle = run_m01(inputs, context)
    handoff = run_m02(bundle=bundle, inputs=inputs, context=context)
    commitment = bundle["commitments"][0]
    assert commitment["readiness"] == "READY_FOR_EVALUATION"

    package, feedback_handoff = build_s3_feedback_handoff(
        evaluation_bundle=bundle,
        context_handoff=handoff,
        outcomes=(
            ReferenceOutcome(
                commitment_id=commitment["commitment_id"],
                outcome_available_at=datetime(2024, 1, 31, 20, 2, tzinfo=timezone.utc),
                outcome_ref={"realized_value": 0.6},
                evaluation_summary={"score": 0.8, "status": "MATURED"},
            ),
        ),
        evaluated_at=datetime(2024, 1, 31, 20, 4, tzinfo=timezone.utc),
        source_cycle_id=1,
        experience_available_from_cycle=2,
    )

    snapshot = deepcopy(governance_outputs["phase3_run_snapshot"])
    result = ingest_feedback(
        {
            "p9_belief_outcome_feedback_package": package,
            "phase3_learning_feedback_handoff_manifest": feedback_handoff,
            "phase3_run_snapshot": snapshot,
        },
        {
            "current_cycle_id": 2,
            "processed_at": "2026-07-27T12:00:00Z",
            "package_root": root,
        },
    )["outputs"]["active_belief_feedback_bundle"]
    assert result["status"] == "ACTIVE"
    assert result["feedback_items"][0]["commitment_id"] == commitment["commitment_id"]
    assert result["feedback_items"][0]["experience_available_from_cycle"] == 2
