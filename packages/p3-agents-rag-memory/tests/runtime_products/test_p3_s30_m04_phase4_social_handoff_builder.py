from __future__ import annotations

import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M04_phase4_social_handoff_builder import (
    IMPLEMENTED,
    MODULE_ID,
    run_module,
)
from quant_pipeline.phase_03_agents_rag_memory.s30_products import S30IntegrityError


def test_module_identity_and_implementation():
    assert MODULE_ID == "P3.S30.M04"
    assert IMPLEMENTED is True


def test_manifest_has_five_payload_entries_and_six_output_semantics(s30_products, s30_execution_context, s30_upstream_inputs):
    result = run_module({
        "social_feature_panel": s30_products["social_feature_panel"],
        "evidence_tag_panel": s30_upstream_inputs["evidence_tag_panel"],
        "agent_disagreement_panel": s30_upstream_inputs["agent_disagreement_panel"],
        "context_memory_feature_panel": s30_products["context_memory_feature_panel"],
        "hypothesis_registry": s30_products["hypothesis_registry"],
        "phase3_run_snapshot": s30_upstream_inputs["phase3_run_snapshot"],
    }, {"execution_context": s30_execution_context})["outputs"]["phase4_social_handoff_manifest"]
    assert result["expected_output_count"] == 6
    assert result["complete"] is True
    assert len(result["entries"]) == 5
    assert {entry["artifact_name"] for entry in result["entries"]} == {
        "social_feature_panel", "evidence_tag_panel", "agent_disagreement_panel",
        "context_memory_feature_panel", "hypothesis_registry",
    }


def test_expected_hash_mismatch_fails(s30_products, s30_execution_context, s30_upstream_inputs):
    with pytest.raises(S30IntegrityError, match="hash mismatch"):
        run_module({
            "social_feature_panel": s30_products["social_feature_panel"],
            "evidence_tag_panel": s30_upstream_inputs["evidence_tag_panel"],
            "agent_disagreement_panel": s30_upstream_inputs["agent_disagreement_panel"],
            "context_memory_feature_panel": s30_products["context_memory_feature_panel"],
            "hypothesis_registry": s30_products["hypothesis_registry"],
            "phase3_run_snapshot": s30_upstream_inputs["phase3_run_snapshot"],
        }, {
            "execution_context": s30_execution_context,
            "expected_artifact_hashes": {"social_feature_panel": "0" * 64},
        })
