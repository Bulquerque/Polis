from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_07_strategy_tournament.finalization.artifacts import sha256_value
from quant_pipeline.phase_07_strategy_tournament.finalization.boundary.base import HandoffManifestRecord
from quant_pipeline.phase_07_strategy_tournament.finalization.boundary.s8_config import S8Config
from quant_pipeline.phase_07_strategy_tournament.finalization.boundary.s8_outputs import RankingAuditRecord, RankingTieRecord
from quant_pipeline.phase_07_strategy_tournament.finalization.errors import ContractViolation, IntegrityViolation
from quant_pipeline.phase_07_strategy_tournament.finalization.runner import run_s8

from .conftest import mutate_record, rebuild, refresh_s7_manifest


def _rewrite_manifest(payload, **updates):
    result = deepcopy(payload)
    record = HandoffManifestRecord.model_validate(
        result["rankability_handoff_manifest"]["records"][0]
    )
    changed = record.model_copy(update=updates)
    result["rankability_handoff_manifest"] = rebuild(
        result["rankability_handoff_manifest"],
        [changed.model_dump(mode="json")],
    )
    return result


@pytest.mark.contract
def test_wrong_s7_consumer_is_rejected(s8_input, s8_config):
    payload = _rewrite_manifest(s8_input, consumer="P7.S9")
    with pytest.raises(ContractViolation) as exc_info:
        run_s8(payload, s8_config)
    assert exc_info.value.code == "P7_S7_HANDOFF_CONTRACT_INVALID"


@pytest.mark.contract
def test_missing_required_manifest_reference_is_rejected(s8_input, s8_config):
    record = HandoffManifestRecord.model_validate(
        s8_input["rankability_handoff_manifest"]["records"][0]
    )
    refs = tuple(ref for ref in record.artifact_references if ref.artifact_name != "comparison_group_panel")
    payload = _rewrite_manifest(s8_input, artifact_references=refs)
    with pytest.raises(ContractViolation) as exc_info:
        run_s8(payload, s8_config)
    assert exc_info.value.code == "P7_S7_HANDOFF_REFERENCE_MISSING"


@pytest.mark.contract
def test_manifest_reference_mismatch_is_rejected(s8_input, s8_config):
    record = HandoffManifestRecord.model_validate(
        s8_input["rankability_handoff_manifest"]["records"][0]
    )
    refs = tuple(
        ref.model_copy(update={"content_sha256": "f" * 64})
        if ref.artifact_name == "comparison_group_panel" else ref
        for ref in record.artifact_references
    )
    payload = _rewrite_manifest(s8_input, artifact_references=refs)
    with pytest.raises(IntegrityViolation) as exc_info:
        run_s8(payload, s8_config)
    assert exc_info.value.code == "P7_S7_HANDOFF_REFERENCE_MISMATCH"


@pytest.mark.adversarial
def test_duplicate_score_head_is_rejected(s8_input, s8_config):
    payload = deepcopy(s8_input)
    rows = list(payload["score_decomposition_panel"]["records"])
    rows.append(dict(rows[0]))
    payload["score_decomposition_panel"] = rebuild(payload["score_decomposition_panel"], rows)
    refresh_s7_manifest(payload)
    with pytest.raises(IntegrityViolation) as exc_info:
        run_s8(payload, s8_config)
    assert exc_info.value.code == "P7_DUPLICATE_SCORE_HEAD"


@pytest.mark.adversarial
def test_terminal_state_overlap_is_rejected(s8_input, s8_config):
    payload = deepcopy(s8_input)
    abstained = list(payload["abstained_candidate_panel"]["records"])
    duplicate = dict(abstained[0])
    duplicate["candidate_id"] = "A"
    abstained.append(duplicate)
    payload["abstained_candidate_panel"] = rebuild(payload["abstained_candidate_panel"], abstained)
    refresh_s7_manifest(payload)
    with pytest.raises(IntegrityViolation) as exc_info:
        run_s8(payload, s8_config)
    assert exc_info.value.code == "P7_TERMINAL_STATE_OVERLAP"


@pytest.mark.adversarial
def test_candidate_count_mismatch_is_rejected(s8_input, s8_config):
    payload = _rewrite_manifest(s8_input, candidate_count=7)
    with pytest.raises(IntegrityViolation) as exc_info:
        run_s8(payload, s8_config)
    assert exc_info.value.code == "P7_CANDIDATE_CONSERVATION_FAILED"


@pytest.mark.adversarial
def test_candidate_conservation_hash_mismatch_is_rejected(s8_input, s8_config):
    payload = _rewrite_manifest(s8_input, candidate_conservation_sha256="f" * 64)
    with pytest.raises(IntegrityViolation) as exc_info:
        run_s8(payload, s8_config)
    assert exc_info.value.code == "P7_CANDIDATE_CONSERVATION_HASH_MISMATCH"


@pytest.mark.adversarial
def test_rankable_candidate_requires_complete_context(s8_input, s8_config):
    payload = deepcopy(s8_input)
    rows = [row for row in payload["comparison_group_panel"]["records"] if row["candidate_id"] != "A"]
    payload["comparison_group_panel"] = rebuild(payload["comparison_group_panel"], rows)
    refresh_s7_manifest(payload)
    with pytest.raises(IntegrityViolation) as exc_info:
        run_s8(payload, s8_config)
    assert exc_info.value.code == "P7_RANKABLE_CONTEXT_MISSING"


@pytest.mark.unit
def test_s8_config_rejects_changed_sort_registry(s8_config):
    payload = deepcopy(s8_config)
    payload["ranking"]["sort_keys"] = ["candidate_id"]
    with pytest.raises(ValidationError):
        S8Config.model_validate(payload)


@pytest.mark.unit
def test_s8_config_rejects_authoritative_llm(s8_config):
    payload = deepcopy(s8_config)
    payload["thesis"]["llm_authoritative"] = True
    with pytest.raises(ValidationError):
        S8Config.model_validate(payload)


@pytest.mark.unit
def test_s8_config_requires_all_publication_references(s8_config):
    payload = deepcopy(s8_config)
    payload["publication"]["required_reference_fields"] = ["strategy_candidate_reference"]
    with pytest.raises(ValidationError):
        S8Config.model_validate(payload)


@pytest.mark.unit
def test_s8_config_consumer_is_p8(s8_config):
    payload = deepcopy(s8_config)
    payload["publication"]["consumer_phase"] = "P9"
    with pytest.raises(ValidationError):
        S8Config.model_validate(payload)


@pytest.mark.unit
def test_tie_record_requires_two_candidates(s8_input):
    decision_time = s8_input["rankable_candidate_panel"]["decision_time"]
    with pytest.raises(ValidationError):
        RankingTieRecord.model_validate({
            "cycle_id": "cycle-1",
            "decision_time": decision_time,
            "comparison_group_id": "G1",
            "economic_tie_id": "tie-1",
            "candidate_ids": ["A"],
            "deterministic_order": ["A"],
            "tie_key_sha256": sha256_value({"tie": "A"}),
            "policy_version": "ranking-v1",
            "lineage_id": "lineage-1",
        })


@pytest.mark.unit
def test_audit_record_enforces_conservation(s8_input):
    decision_time = s8_input["rankable_candidate_panel"]["decision_time"]
    with pytest.raises(ValidationError):
        RankingAuditRecord.model_validate({
            "run_id": "run-1",
            "cycle_id": "cycle-1",
            "decision_time": decision_time,
            "received_count": 4,
            "ranked_count": 1,
            "abstained_count": 1,
            "blocked_count": 1,
            "candidate_conservation_pass": True,
            "group_count": 1,
            "tie_count": 0,
            "policy_versions": {},
            "model_versions": [],
            "input_artifact_hashes": {},
            "output_artifact_hashes": {},
            "lineage_id": "lineage-1",
        })
