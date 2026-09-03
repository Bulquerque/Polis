from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S31_M01_p9_evaluation_evidence_bundle_builder import (
    IMPLEMENTED,
    MODULE_ID,
    MODULE_NAME,
    REQUIRED_INPUTS,
    run_module,
)
from quant_pipeline.phase_03_agents_rag_memory.s31_products import (
    S31AuthorityError,
    S31IntegrityError,
    S31TemporalError,
)
from .s31_support import execution_context, m01_inputs, run_m01


def test_module_identity_and_status():
    assert MODULE_ID == "P3.S31.M01"
    assert MODULE_NAME == "p9_evaluation_evidence_bundle_builder"
    assert IMPLEMENTED is True
    assert len(REQUIRED_INPUTS) == 6


def test_builds_complete_outcome_blind_bundle():
    bundle = run_m01()
    assert bundle["complete"] is True
    assert bundle["evaluation_authority"] == "P9"
    assert bundle["contains_evaluation_results"] is False
    assert bundle["contains_outcome_labels"] is False
    assert bundle["contains_promotion_decision"] is False
    assert len(bundle["items"]) == 6
    assert {row["artifact_name"] for row in bundle["items"]} == set(REQUIRED_INPUTS)
    assert bundle["blind_holdout_policy"]["same_cycle_feedback_allowed"] is False
    assert bundle["reproducibility"]["snapshot_id"] == "snapshot-s30-fixture"


def test_commitment_schedule_is_pending_before_maturity():
    bundle = run_m01()
    assert bundle["commitments"][0]["readiness"] == "PENDING_MATURITY"


def test_commitment_schedule_becomes_ready_after_maturity():
    context = execution_context()
    context["created_at"] = "2024-02-22T00:00:00Z"
    bundle = run_m01(context=context)
    assert bundle["commitments"][0]["readiness"] == "READY_FOR_EVALUATION"


def test_empty_commitment_log_is_valid_but_degraded():
    inputs = m01_inputs()
    inputs["belief_outcome_commitment_log"]["records"] = []
    bundle = run_m01(inputs)
    assert bundle["commitments"] == []
    assert bundle["quality_status"] == "DEGRADED"
    assert "NO_BELIEF_COMMITMENTS" in bundle["quality_reasons"]


@pytest.mark.parametrize(
    ("risk", "expected_status"),
    [("STRICT_CLEAN", "PASS"), ("LOWER_RISK", "PASS"), ("UNKNOWN", "DEGRADED"), ("CONTAMINATION_RISK", "BLOCKED")],
)
def test_cutoff_risk_rollup(risk, expected_status):
    inputs = m01_inputs()
    inputs["model_knowledge_cutoff_report"]["risk_class"] = risk
    bundle = run_m01(inputs)
    assert bundle["quality_status"] == expected_status


def test_rejects_commitment_after_as_of():
    inputs = m01_inputs()
    inputs["belief_outcome_commitment_log"]["records"][0]["committed_at"] = "2024-02-01T00:00:00Z"
    with pytest.raises(S31TemporalError, match="created after run as_of_time"):
        run_m01(inputs)


def test_rejects_cutoff_window_after_as_of():
    inputs = m01_inputs()
    inputs["model_knowledge_cutoff_report"]["evaluation_end"] = "2024-02-01T00:00:00Z"
    with pytest.raises(S31TemporalError, match="evaluation_end"):
        run_m01(inputs)


def test_rejects_variable_reference_mismatch():
    inputs = m01_inputs()
    inputs["variable_evolution_input_manifest"]["canonical_society_state_ref"] = "wrong"
    with pytest.raises(S31IntegrityError, match="society-state reference"):
        run_m01(inputs)


def test_rejects_recursive_evaluation_field():
    inputs = m01_inputs()
    inputs["model_knowledge_cutoff_report"]["evaluation_results"] = {"sharpe": 2.0}
    with pytest.raises(S31AuthorityError, match="evaluation_results"):
        run_m01(inputs)


def test_wrapper_requires_explicit_context():
    with pytest.raises(ValueError, match="execution context"):
        run_module({}, {})


def test_input_record_order_does_not_change_bundle():
    inputs = m01_inputs()
    # Add a second commitment, then reverse it. Content hashes and output order remain canonical.
    second = deepcopy(inputs["belief_outcome_commitment_log"]["records"][0])
    second["commitment_id"] = "commitment-000"
    second["commitment_hash"] = "d" * 64
    second["person_id"] = "person-000"
    second["lineage_id"] = "lineage-commitment-000"
    inputs["belief_outcome_commitment_log"]["records"].append(second)
    first = run_m01(inputs)
    inputs["belief_outcome_commitment_log"]["records"].reverse()
    second_output = run_m01(inputs)
    assert first == second_output
