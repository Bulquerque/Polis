from __future__ import annotations

import pytest

from quant_pipeline.phase_07_strategy_tournament.finalization.runner import run_s8

from .conftest import mutate_record


@pytest.mark.integration
def test_thesis_is_structured_and_evidence_bound(s8_input, s8_config):
    output = run_s8(s8_input, s8_config)
    cards = {row["candidate_id"]: row for row in output["strategy_thesis_card_panel"]["records"]}
    assert cards["A"]["belief_reference_ids"] == ["belief:A:return", "belief:A:volatility"]
    assert cards["A"]["nearest_alternative_ids"] == ["B"]
    assert cards["A"]["score_contributions"]["robustness"] == 0.75
    assert cards["A"]["section_availability"]["failure_regions"] == "AVAILABLE"
    assert cards["A"]["evidence_artifact_ids"]


@pytest.mark.adversarial
def test_missing_thesis_section_is_marked_unavailable_not_invented(s8_input, s8_config):
    payload = mutate_record(
        s8_input,
        "validated_strategy_candidate_reference_panel",
        "A",
        belief_reference_ids=[],
        profit_regions=[],
    )
    output = run_s8(payload, s8_config)
    card = next(row for row in output["strategy_thesis_card_panel"]["records"] if row["candidate_id"] == "A")
    assert card["belief_reference_ids"] == []
    assert card["profit_regions"] == []
    assert card["section_availability"]["belief_references"] == "UNAVAILABLE"
    assert card["section_availability"]["profit_regions"] == "UNAVAILABLE"


@pytest.mark.contract
def test_audit_conserves_all_terminal_states(s8_input, s8_config):
    output = run_s8(s8_input, s8_config)
    audit = output["ranking_audit_report"]["records"][0]
    assert audit["received_count"] == 6
    assert audit["ranked_count"] + audit["abstained_count"] + audit["blocked_count"] == 6
    assert audit["candidate_conservation_pass"] is True
    assert audit["policy_versions"]["ranking"] == "p7_ranking_v1"
    assert audit["model_versions"] == ["ltr-champion-1"]
