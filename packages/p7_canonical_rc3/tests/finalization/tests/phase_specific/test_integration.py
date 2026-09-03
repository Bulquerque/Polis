from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.finalization.artifacts import ArtifactEnvelope, validate_artifact_integrity
from quant_pipeline.phase_07_strategy_tournament.finalization.runner import run_s7

from .conftest import mutate_record, permute_records


@pytest.mark.integration
def test_full_s7_flow_has_expected_terminal_states(input_payload, s7_config):
    result = run_s7(input_payload, s7_config)
    rankable = {record["candidate_id"] for record in result["rankable_candidate_panel"]["records"]}
    abstained = {record["candidate_id"] for record in result["abstained_candidate_panel"]["records"]}
    blocked = {record["candidate_id"] for record in result["final_blocked_candidate_panel"]["records"]}
    assert rankable == {"A", "B", "E"}
    assert abstained == {"C", "F"}
    assert blocked == {"D"}
    assert rankable.isdisjoint(abstained | blocked)
    assert rankable | abstained | blocked == {"A", "B", "C", "D", "E", "F"}


@pytest.mark.integration
def test_handoff_manifest_references_all_outputs(input_payload, s7_config):
    result = run_s7(input_payload, s7_config)
    manifest = result["rankability_handoff_manifest"]
    record = manifest["records"][0]
    refs = {ref["artifact_name"]: ref for ref in record["artifact_references"]}
    for name in ("rankable_candidate_panel", "abstained_candidate_panel", "final_blocked_candidate_panel"):
        assert refs[name]["artifact_id"] == result[name]["artifact_id"]
        assert refs[name]["content_sha256"] == result[name]["content_sha256"]
    for name, artifact in result.items():
        if name == "module_execution_receipts":
            continue
        validate_artifact_integrity(ArtifactEnvelope.model_validate(artifact), "TEST")


@pytest.mark.replay
def test_full_flow_is_deterministic_under_record_permutation(input_payload, s7_config):
    direct = run_s7(input_payload, s7_config)
    permuted = run_s7(permute_records(input_payload), s7_config)
    assert {k: v for k, v in direct.items() if k != "module_execution_receipts"} == {
        k: v for k, v in permuted.items() if k != "module_execution_receipts"
    }


@pytest.mark.integration
def test_runner_does_not_mutate_inputs(input_payload, s7_config):
    original = deepcopy(input_payload)
    run_s7(input_payload, s7_config)
    assert input_payload == original


@pytest.mark.adversarial
def test_severe_ood_reaches_final_block(input_payload, s7_config):
    mutated = mutate_record(input_payload, "candidate_score_confidence_panel", "C", ood_severity="SEVERE")
    result = run_s7(mutated, s7_config)
    blocked = {record["candidate_id"]: record for record in result["final_blocked_candidate_panel"]["records"]}
    assert "C" in blocked
    assert "P7_SEVERE_OOD_BLOCK_POLICY" in blocked["C"]["reason_codes"]
