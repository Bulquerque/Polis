from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.finalization.boundary.base import ArtifactEnvelope
from quant_pipeline.phase_07_strategy_tournament.finalization.boundary.s8_outputs import Phase8ManifestRecord
from quant_pipeline.phase_07_strategy_tournament.finalization.errors import IntegrityViolation, TemporalViolation
from quant_pipeline.phase_07_strategy_tournament.finalization.runner import run_s8

from .conftest import mutate_record


@pytest.mark.integration
def test_multi_leg_context_is_preserved_by_references(s8_input, s8_config):
    output = run_s8(s8_input, s8_config)
    snapshots = {row["candidate_id"]: row for row in output["ranked_strategy_execution_context_snapshot"]["records"]}
    expected_legs = next(row["leg_ids"] for row in s8_input["validated_strategy_candidate_reference_panel"]["records"] if row["candidate_id"] == "A")
    assert snapshots["A"]["leg_ids"] == expected_legs
    assert snapshots["A"]["strategy_legs_reference"]["record_count"] == 2
    assert snapshots["A"]["payoff_evaluation_reference"]["artifact_name"] == "strategy_payoff_panel"
    legacy = {row["candidate_id"]: row for row in output["compatibility_projection_report"]["records"]}
    assert legacy["A"]["projection_status"] == "UNSUPPORTED_MULTI_LEG"


@pytest.mark.adversarial
def test_missing_execution_reference_fails_closed(s8_input, s8_config):
    payload = mutate_record(
        s8_input,
        "validated_strategy_candidate_reference_panel",
        "A",
        strategy_legs_reference=None,
    )
    with pytest.raises(IntegrityViolation) as exc_info:
        run_s8(payload, s8_config)
    assert exc_info.value.code == "P7_CONTEXT_JOIN_MISSING"


@pytest.mark.property
def test_p8_manifest_hash_changes_when_context_reference_changes(s8_input, s8_config):
    original = run_s8(s8_input, s8_config)
    row = next(item for item in s8_input["validated_strategy_candidate_reference_panel"]["records"] if item["candidate_id"] == "A")
    changed_ref = dict(row["risk_reference"])
    changed_ref["content_sha256"] = "f" * 64
    payload = mutate_record(s8_input, "validated_strategy_candidate_reference_panel", "A", risk_reference=changed_ref)
    changed = run_s8(payload, s8_config)
    assert original["phase8_strategy_ranking_handoff_manifest"]["content_sha256"] != changed["phase8_strategy_ranking_handoff_manifest"]["content_sha256"]


@pytest.mark.contract
def test_p8_consumer_contract_references_all_published_artifacts(s8_input, s8_config):
    output = run_s8(s8_input, s8_config)
    envelope = ArtifactEnvelope.model_validate(output["phase8_strategy_ranking_handoff_manifest"])
    record = Phase8ManifestRecord.model_validate(envelope.records[0])
    available = dict(s8_input)
    available.update({name: value for name, value in output.items() if name != "module_execution_receipts"})
    for ref in record.artifact_references:
        target = ArtifactEnvelope.model_validate(available[ref.artifact_name])
        assert target.artifact_id == ref.artifact_id
        assert target.content_sha256 == ref.content_sha256
        assert target.schema_version == ref.schema_version
        assert target.record_count == ref.record_count
    assert record.consumer_phase == "P8"
    assert record.contract_version == "2.0.0"


@pytest.mark.temporal
def test_nested_future_field_is_rejected(s8_input, s8_config):
    payload = deepcopy(s8_input)
    payload["untrusted"] = {"nested": {"future_return": 999.0}}
    with pytest.raises(TemporalViolation) as exc_info:
        run_s8(payload, s8_config)
    assert exc_info.value.code == "P7_FUTURE_FIELD_DETECTED"


@pytest.mark.contract
def test_strategy_candidate_reference_can_be_derived_from_frozen_fields(s8_input, s8_config):
    payload = mutate_record(
        s8_input,
        "validated_strategy_candidate_reference_panel",
        "A",
        strategy_candidate_reference=None,
    )
    output = run_s8(payload, s8_config)
    snapshot = next(
        row for row in output["ranked_strategy_execution_context_snapshot"]["records"]
        if row["candidate_id"] == "A"
    )
    assert snapshot["strategy_candidate_reference"]["artifact_id"] == "strategy-A"
    assert snapshot["strategy_candidate_reference"]["record_count"] == 1


@pytest.mark.contract
def test_single_leg_legacy_projection_is_supported_only_with_complete_context(s8_input, s8_config):
    payload = mutate_record(s8_input, "rankable_candidate_panel", "E", leg_count=1)
    payload = mutate_record(
        payload,
        "validated_strategy_candidate_reference_panel",
        "E",
        leg_ids=["LEG-E"],
        legacy_underlying="TEST3",
        legacy_instrument_type="OPTION",
        legacy_action_type="BUY",
        legacy_reference_price=5.25,
        legacy_contract_key="TEST3-C-100-20261218",
        legacy_expiration_date="2026-12-18",
        legacy_strike=100.0,
        legacy_dte=139,
        legacy_cost_estimate=5.30,
        legacy_liquidity_score=0.82,
    )
    output = run_s8(payload, s8_config)
    legacy = next(row for row in output["compatibility_projection_report"]["records"] if row["candidate_id"] == "E")
    assert legacy["projection_status"] == "SUPPORTED"
    assert legacy["reason_code"] is None


@pytest.mark.contract
def test_single_leg_legacy_projection_refuses_missing_context(s8_input, s8_config):
    payload = mutate_record(s8_input, "rankable_candidate_panel", "E", leg_count=1)
    payload = mutate_record(
        payload,
        "validated_strategy_candidate_reference_panel",
        "E",
        leg_ids=["LEG-E"],
    )
    output = run_s8(payload, s8_config)
    legacy = next(row for row in output["compatibility_projection_report"]["records"] if row["candidate_id"] == "E")
    assert legacy["projection_status"] == "UNAVAILABLE_CONTEXT"
    assert legacy["reason_code"] == "P7_CONTEXT_JOIN_MISSING"
