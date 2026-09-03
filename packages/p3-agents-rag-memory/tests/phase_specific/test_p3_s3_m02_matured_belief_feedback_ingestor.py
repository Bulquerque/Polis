from __future__ import annotations

import copy
import pytest

from quant_pipeline.phase_03_agents_rag_memory.foundation.learning_feedback.errors import S3ContractError
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S3_M02_matured_belief_feedback_ingestor import run_module


def _inputs(governance_outputs):
    snapshot = copy.deepcopy(governance_outputs["phase3_run_snapshot"])
    lineage = "lineage-p9-feedback-empty"
    package = {
        "schema_version": "v14.1-rc4.1",
        "contract_version": "p9.p3.belief_outcome_feedback.v1",
        "artifact_id": "belief-feedback-empty",
        "created_at": "2026-07-26T00:00:00Z",
        "lineage_id": lineage,
        "status": "NO_MATURED_FEEDBACK",
        "feedback_items": [],
    }
    manifest = {
        "schema_version": "v14.1-rc4.1",
        "contract_version": "p9.p3.learning_feedback_handoff.v1",
        "artifact_id": "belief-feedback-manifest-empty",
        "created_at": "2026-07-26T00:00:00Z",
        "lineage_id": lineage,
        "status": "NO_MATURED_FEEDBACK",
        "feedback_artifact_id": package["artifact_id"],
    }
    return {
        "p9_belief_outcome_feedback_package": package,
        "phase3_learning_feedback_handoff_manifest": manifest,
        "phase3_run_snapshot": snapshot,
    }


def test_no_matured_feedback_is_explicit(root, governance_outputs):
    output = run_module(_inputs(governance_outputs), {"current_cycle_id": 2, "processed_at": "2026-07-27T12:00:00Z", "package_root": root})
    bundle = output["outputs"]["active_belief_feedback_bundle"]
    assert bundle["status"] == "NO_MATURED_FEEDBACK"
    assert bundle["feedback_items"] == []


def test_future_feedback_handoff_is_rejected(root, governance_outputs):
    inputs = _inputs(governance_outputs)
    inputs["p9_belief_outcome_feedback_package"]["created_at"] = "2026-07-28T00:00:00Z"
    with pytest.raises(S3ContractError, match="FUTURE_HANDOFF"):
        run_module(inputs, {"current_cycle_id": 2, "processed_at": "2026-07-27T12:00:00Z", "package_root": root})
