from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.finalization.errors import IntegrityViolation, TemporalViolation
from quant_pipeline.phase_07_strategy_tournament.finalization.modules import (
    P7_S7_M01_candidate_similarity_graph_builder as m01,
    P7_S7_M02_diversity_adjustment_engine as m02,
    P7_S7_M03_final_candidate_safety_gate as m03,
)
from quant_pipeline.phase_07_strategy_tournament.finalization.runner import run_s7

from .conftest import rebuild_envelope, refresh_scoring_manifest, remove_record


@pytest.mark.temporal
def test_nested_future_field_is_rejected_before_record_parsing(input_payload, s7_config):
    mutated = deepcopy(input_payload)
    records = deepcopy(mutated["validated_strategy_candidate_reference_panel"]["records"])
    records[0]["extensions"] = {"nested": {"future_return": 999.0}}
    mutated["validated_strategy_candidate_reference_panel"] = rebuild_envelope(
        mutated["validated_strategy_candidate_reference_panel"], records
    )
    refresh_scoring_manifest(mutated)
    with pytest.raises(TemporalViolation) as exc_info:
        run_s7(mutated, s7_config)
    assert exc_info.value.code == "P7_FUTURE_FIELD_DETECTED"


@pytest.mark.adversarial
def test_tampered_artifact_hash_is_rejected(input_payload, s7_config):
    mutated = deepcopy(input_payload)
    mutated["hybrid_candidate_score_panel"]["records"][0]["hybrid_score"] = 999.0
    with pytest.raises(IntegrityViolation) as exc_info:
        run_s7(mutated, s7_config)
    assert exc_info.value.code == "P7_ARTIFACT_HASH_MISMATCH"


@pytest.mark.adversarial
def test_missing_diversity_score_candidate_is_rejected(input_payload, s7_config):
    m01_result = m01.run_module(input_payload, s7_config)
    m02_inputs = {**input_payload, **{k: v for k, v in m01_result.items() if k != "module_execution_receipt"}}
    m02_result = m02.run_module(m02_inputs, s7_config)
    m03_inputs = {**m02_inputs, **{k: v for k, v in m02_result.items() if k != "module_execution_receipt"}}
    score_env = m03_inputs["diversity_adjusted_score_panel"]
    score_env = rebuild_envelope(score_env, [r for r in score_env["records"] if r["candidate_id"] != "A"])
    m03_inputs["diversity_adjusted_score_panel"] = score_env
    with pytest.raises(IntegrityViolation) as exc_info:
        m03.run_module(m03_inputs, s7_config)
    assert exc_info.value.code == "P7_SCORE_CANDIDATE_SET_MISMATCH"


@pytest.mark.adversarial
def test_candidate_set_mismatch_in_learning_handoff_is_rejected(input_payload, s7_config):
    mutated = remove_record(input_payload, "candidate_score_confidence_panel", "F")
    with pytest.raises(IntegrityViolation) as exc_info:
        run_s7(mutated, s7_config)
    assert exc_info.value.code in {"P7_CANDIDATE_RECONCILIATION_FAILED", "P7_MANIFEST_CANDIDATE_COUNT_MISMATCH"}
