from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S25_M01_trust_relationship_updater import (
    run_module as run_m01,
)
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S25_M02_social_relationship_tool_executor import (
    run_module,
)
from quant_pipeline.phase_03_agents_rag_memory.s25.errors import S25PolicyError

pytestmark = pytest.mark.unit


def updated_graph(valid_fixture, config_fixture):
    return run_m01(
        {
            "current_social_graph": valid_fixture("current_social_graph.json"),
            "social_delivery_panel": valid_fixture("social_delivery_panel.json"),
            "validated_next_person_state_panel": valid_fixture(
                "validated_next_person_state_panel.json"
            ),
            "active_belief_feedback_bundle": valid_fixture(
                "active_belief_feedback_bundle.json"
            ),
            "relationship_update_config": config_fixture("RELATIONSHIP_UPDATE_CONFIG.yaml"),
        }
    )["updated_social_graph"]


def inputs(valid_fixture, config_fixture):
    return {
        "updated_social_graph": updated_graph(valid_fixture, config_fixture),
        "social_tool_audit_panel": valid_fixture("social_tool_audit_panel.json"),
        "active_retro_policy_patch": valid_fixture("active_retro_policy_patch.json"),
        "relationship_formation_config": config_fixture(
            "RELATIONSHIP_FORMATION_CONFIG.yaml"
        ),
    }


def test_three_valid_interactions_create_eligible_proposal(valid_fixture, config_fixture):
    result = run_module(inputs(valid_fixture, config_fixture))["relationship_candidate_panel"]
    assert len(result["records"]) == 1
    record = result["records"][0]
    assert record["eligibility_status"] == "ELIGIBLE"
    assert record["interaction_count"] == 3
    assert record["mean_mutual_relevance"] == pytest.approx(0.8)


def test_insufficient_interactions_are_deferred(valid_fixture, config_fixture):
    payload = inputs(valid_fixture, config_fixture)
    payload["social_tool_audit_panel"]["records"] = payload["social_tool_audit_panel"][
        "records"
    ][:2]
    record = run_module(payload)["relationship_candidate_panel"]["records"][0]
    assert record["eligibility_status"] == "DEFERRED_INSUFFICIENT_EVIDENCE"
    assert "insufficient_interactions" in record["criteria_failed"]


def test_named_edge_retro_patch_is_forbidden(
    valid_fixture,
    invalid_fixture,
    config_fixture,
):
    payload = inputs(valid_fixture, config_fixture)
    payload["active_retro_policy_patch"] = invalid_fixture("named_edge_retro_patch.json")
    with pytest.raises(S25PolicyError):
        run_module(payload)


def test_existing_edge_is_rejected_by_policy(valid_fixture, config_fixture):
    payload = inputs(valid_fixture, config_fixture)
    for record in payload["social_tool_audit_panel"]["records"]:
        record["target_person_id"] = "p2"
        record["relationship_type"] = "peer"
    proposal = run_module(payload)["relationship_candidate_panel"]["records"][0]
    assert proposal["eligibility_status"] == "REJECTED_POLICY"
    assert "edge_already_exists" in proposal["criteria_failed"]


def test_input_order_does_not_change_output(valid_fixture, config_fixture):
    first = inputs(valid_fixture, config_fixture)
    second = deepcopy(first)
    second["social_tool_audit_panel"]["records"].reverse()
    out_a = run_module(first)["relationship_candidate_panel"]
    out_b = run_module(second)["relationship_candidate_panel"]
    assert out_a == out_b
