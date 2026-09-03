from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S25_M01_trust_relationship_updater import (
    run_module,
)
from quant_pipeline.phase_03_agents_rag_memory.s25.errors import (
    S25ContractError,
    S25TemporalError,
)

pytestmark = pytest.mark.unit


def inputs(valid_fixture, config_fixture):
    return {
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


def test_updates_only_observed_domain_and_respects_cap(valid_fixture, config_fixture):
    result = run_module(inputs(valid_fixture, config_fixture))["updated_social_graph"]
    edge = next(record for record in result["records"] if record["edge_id"] == "edge_p1_p2")
    assert edge["trust_by_domain"]["source_reliability"] == pytest.approx(0.55)
    assert edge["trust_by_domain"]["technical_skill"] == 0.5
    assert edge["general_trust"] == pytest.approx(0.51)
    assert len(result["changes"]) == 1
    assert abs(result["changes"][0]["applied_delta"]) <= 0.05


def test_unmatured_feedback_does_not_change_trust(valid_fixture, config_fixture):
    payload = inputs(valid_fixture, config_fixture)
    payload["validated_next_person_state_panel"]["records"][0][
        "relationship_observations"
    ] = []
    payload["active_belief_feedback_bundle"]["items"][0]["status"] = "NOT_MATURED"
    result = run_module(payload)["updated_social_graph"]
    edge = next(record for record in result["records"] if record["edge_id"] == "edge_p1_p2")
    assert edge["trust_by_domain"]["source_reliability"] == 0.5
    assert result["changes"] == []


def test_future_delivery_fails_closed(valid_fixture, invalid_fixture, config_fixture):
    payload = inputs(valid_fixture, config_fixture)
    payload["social_delivery_panel"] = invalid_fixture("future_social_delivery_panel.json")
    with pytest.raises(S25TemporalError):
        run_module(payload)


def test_undeclared_input_is_rejected(valid_fixture, config_fixture):
    payload = inputs(valid_fixture, config_fixture)
    payload["hidden_state"] = {}
    with pytest.raises(S25ContractError, match="undeclared inputs"):
        run_module(payload)


def test_forbidden_economic_field_is_rejected(valid_fixture, config_fixture):
    payload = inputs(valid_fixture, config_fixture)
    payload = deepcopy(payload)
    payload["current_social_graph"]["future_return"] = 1.0
    with pytest.raises(S25ContractError, match="forbidden field"):
        run_module(payload)


def test_emits_structured_observability(valid_fixture, config_fixture, caplog):
    caplog.set_level("INFO")
    run_module(inputs(valid_fixture, config_fixture))
    events = [getattr(record, "p3", {}).get("event") for record in caplog.records]
    assert "module_started" in events
    assert "module_succeeded" in events


def test_created_message_does_not_change_trust(valid_fixture, config_fixture):
    payload = inputs(valid_fixture, config_fixture)
    payload["social_delivery_panel"]["records"][0]["status"] = "CREATED"
    payload["active_belief_feedback_bundle"]["items"] = []
    result = run_module(payload)["updated_social_graph"]
    edge = next(record for record in result["records"] if record["edge_id"] == "edge_p1_p2")
    # A merely created message has not been observed and cannot update trust.
    assert edge["trust_by_domain"]["source_reliability"] == 0.5
    assert result["changes"] == []
