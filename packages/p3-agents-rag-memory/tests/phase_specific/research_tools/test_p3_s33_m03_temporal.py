from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.contracts.boundary_artifacts import (
    PitVisibilityPolicy,
    VintagePolicyName,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.services.temporal_boundary import (
    filter_visible_records,
)

from .support_s33 import DECISION_TIME, build_s33_m03, digest, load_yaml


def test_m03_builds_backtest_policy_and_vintage_registry():
    out = build_s33_m03()
    assert out["pit_visibility_policy"]["decision_time"] == DECISION_TIME
    assert out["pit_visibility_policy"]["require_request_as_of_equals_decision_time"] is True
    assert out["vintage_policy_registry"]["default_policy"] == "KNOWN_AT_DECISION_TIME"
    assert out["pit_boundary_qualification_report"]["overall_status"] == "PASS"


def test_filter_visible_records_rejects_future_and_missing_time():
    out = build_s33_m03()
    policy = PitVisibilityPolicy.model_validate(out["pit_visibility_policy"], strict=False)
    records = [
        {"id": 1, "available_at": "2024-01-10T00:00:00Z"},
        {"id": 2, "available_at": "2024-01-20T00:00:00Z"},
        {"id": 3},
    ]
    visible, proof = filter_visible_records(
        records,
        policy=policy,
        request_as_of=datetime.fromisoformat(DECISION_TIME.replace("Z", "+00:00")),
        vintage_policy=VintagePolicyName.KNOWN_AT_DECISION_TIME,
        p1_snapshot_id="p1",
        p2_snapshot_id="p2",
        input_hashes=(digest("input"),),
    )
    assert [item["id"] for item in visible] == [1]
    assert proof.records_rejected_future == 1
    assert proof.records_rejected_missing_time == 1


def test_visibility_is_monotone_when_decision_time_moves_backward():
    out = build_s33_m03()
    current = PitVisibilityPolicy.model_validate(out["pit_visibility_policy"], strict=False)
    records = [
        {"id": 1, "available_at": "2024-01-01T00:00:00Z"},
        {"id": 2, "available_at": "2024-01-12T00:00:00Z"},
    ]
    visible_current, _ = filter_visible_records(
        records, policy=current, request_as_of=current.decision_time,
        vintage_policy=VintagePolicyName.KNOWN_AT_DECISION_TIME,
        p1_snapshot_id="p1", p2_snapshot_id="p2", input_hashes=(digest("a"),),
    )
    previous = current.model_copy(update={"decision_time": datetime(2024, 1, 5, tzinfo=timezone.utc)})
    visible_previous, _ = filter_visible_records(
        records, policy=previous, request_as_of=previous.decision_time,
        vintage_policy=VintagePolicyName.KNOWN_AT_DECISION_TIME,
        p1_snapshot_id="p1", p2_snapshot_id="p2", input_hashes=(digest("a"),),
    )
    assert len(visible_previous) <= len(visible_current)


def test_filter_rejects_request_as_of_different_from_decision_time():
    policy = PitVisibilityPolicy.model_validate(build_s33_m03()["pit_visibility_policy"], strict=False)
    with pytest.raises(ValueError, match="must equal"):
        filter_visible_records(
            [], policy=policy, request_as_of=datetime(2024, 1, 14, tzinfo=timezone.utc),
            vintage_policy=VintagePolicyName.KNOWN_AT_DECISION_TIME,
            p1_snapshot_id="p1", p2_snapshot_id="p2", input_hashes=(),
        )


def test_m03_forbidden_default_vintage_fails_closed():
    config = load_yaml("config/research_tools/PIT_DATA_VIEW_POLICY.yaml")
    config = deepcopy(config)
    config["forbidden_backtest_vintage_policies"].append("KNOWN_AT_DECISION_TIME")
    out = build_s33_m03(overrides={"pit_data_view_policy_config": config})
    assert out["pit_boundary_qualification_report"]["overall_status"] == "FAIL"


def test_m03_rejects_naive_decision_time():
    with pytest.raises(ValueError, match="naive"):
        build_s33_m03(overrides={
            "phase3_run_snapshot": {"snapshot_id": "x", "decision_time": "2024-01-15T12:00:00", "execution_mode": "BACKTEST"},
            "evaluation_window_config": {"decision_time": "2024-01-15T12:00:00"},
        })
