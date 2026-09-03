from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M05_variable_evolution_handoff_builder import (
    IMPLEMENTED,
    MODULE_ID,
    run_module,
)
from quant_pipeline.phase_03_agents_rag_memory.s30_products import S30ContractError


def test_module_identity_and_implementation():
    assert MODULE_ID == "P3.S30.M05"
    assert IMPLEMENTED is True


def test_reference_only_manifest_has_exact_contract(s30_products, s30_execution_context, s30_upstream_inputs):
    output = run_module({
        "validated_society_state_panel": s30_upstream_inputs["validated_society_state_panel"],
        "social_feature_panel": s30_products["social_feature_panel"],
        "context_memory_feature_panel": s30_products["context_memory_feature_panel"],
        "hypothesis_registry": s30_products["hypothesis_registry"],
        "belief_outcome_commitment_log": s30_upstream_inputs["belief_outcome_commitment_log"],
        "phase3_run_snapshot": s30_upstream_inputs["phase3_run_snapshot"],
    }, {"execution_context": s30_execution_context})["outputs"]["variable_evolution_input_manifest"]
    assert set(output) == {
        "manifest_id", "canonical_society_state_ref", "social_feature_ref",
        "context_memory_feature_ref", "hypothesis_registry_ref",
        "belief_commitment_ref", "as_of_time", "lineage_id",
    }
    assert "feature_genome" not in output
    assert "candidate_score" not in output


def test_snapshot_mismatch_fails(s30_products, s30_execution_context, s30_upstream_inputs):
    broken = deepcopy(s30_upstream_inputs)
    broken["phase3_run_snapshot"]["cycle_id"] = "other-cycle"
    with pytest.raises(S30ContractError, match="snapshot"):
        run_module({
            "validated_society_state_panel": broken["validated_society_state_panel"],
            "social_feature_panel": s30_products["social_feature_panel"],
            "context_memory_feature_panel": s30_products["context_memory_feature_panel"],
            "hypothesis_registry": s30_products["hypothesis_registry"],
            "belief_outcome_commitment_log": broken["belief_outcome_commitment_log"],
            "phase3_run_snapshot": broken["phase3_run_snapshot"],
        }, {"execution_context": s30_execution_context})
