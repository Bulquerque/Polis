from __future__ import annotations

from copy import deepcopy
import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S27_M03_cascade_emergence_metrics import run_module
from quant_pipeline.phase_03_agents_rag_memory.s27.errors import S27CausalityError, S27TemporalError
from s27_test_support import m03_inputs


def test_golden_cascade_exact() -> None:
    records = run_module(m03_inputs())["cascade_metrics_panel"]["records"]
    petr = records[0]
    vale = records[1]
    assert petr["cascade_count"] == 1
    assert petr["max_cascade_size"] == 7
    assert petr["max_cascade_depth"] == 6
    assert petr["mean_cascade_duration_seconds"] == 18000.0
    assert petr["secondary_activation_rate"] == 1.0
    assert petr["social_contagion"] == 1.0
    assert petr["influence_concentration"] == 1.0
    assert vale["max_cascade_size"] == 1
    assert vale["max_cascade_depth"] == 0


def test_delivered_but_unseen_message_is_not_causal_node() -> None:
    record = run_module(m03_inputs())["cascade_metrics_panel"]["records"][0]
    node_ids = record["cascades"][0]["node_ids"]
    assert "ignored" not in node_ids


def test_missing_parent_is_unlinked_and_degrades_group() -> None:
    inputs = m03_inputs()
    inputs["activation_panel"]["records"].append({
        "activation_id": "a-missing", "person_id": "p1", "stimulus_id": "s1",
        "activation_reason": "SOCIAL_MESSAGE", "activation_score": 0.6, "threshold": 0.5,
        "scheduled_at": "2026-06-09T06:00:00Z", "causal_parent_id": "missing-parent",
        "underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d",
        "lineage_id": "lin-missing",
    })
    record = run_module(inputs)["cascade_metrics_panel"]["records"][0]
    assert record["status"] == "DEGRADED"
    assert record["unlinked_event_count"] == 1


def test_causal_cycle_fails() -> None:
    inputs = m03_inputs()
    inputs["activation_panel"]["records"] = [
        {"activation_id": "x1", "person_id": "p1", "stimulus_id": "s1", "activation_reason": "SOCIAL_MESSAGE", "activation_score": 0.7, "threshold": 0.5, "scheduled_at": "2026-06-09T01:00:00Z", "causal_parent_id": "x2", "underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "lineage_id": "lx1"},
        {"activation_id": "x2", "person_id": "p2", "stimulus_id": "s1", "activation_reason": "SOCIAL_MESSAGE", "activation_score": 0.7, "threshold": 0.5, "scheduled_at": "2026-06-09T02:00:00Z", "causal_parent_id": "x1", "underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "lineage_id": "lx2"},
    ]
    inputs["social_delivery_panel"]["records"] = []
    inputs["social_tool_audit_panel"]["records"] = []
    with pytest.raises(S27CausalityError, match="cycle"):
        run_module(inputs)


def test_future_delivery_fails() -> None:
    inputs = m03_inputs()
    inputs["social_delivery_panel"]["records"][0]["status_at"] = "2026-06-11T00:00:00Z"
    with pytest.raises(S27TemporalError):
        run_module(inputs)


def test_input_order_independent() -> None:
    inputs = m03_inputs()
    reordered = deepcopy(inputs)
    reordered["activation_panel"]["records"].reverse()
    reordered["stimulus_panel"]["records"].reverse()
    reordered["social_delivery_panel"]["records"].reverse()
    assert run_module(inputs) == run_module(reordered)
