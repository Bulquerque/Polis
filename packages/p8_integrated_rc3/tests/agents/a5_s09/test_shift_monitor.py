import json
from copy import deepcopy
from datetime import timedelta

import pytest

from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.enums import ShiftState
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.models_shift import ShiftMonitorRequest
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.shift_monitor import run_shift_monitor


def _request(fixture_payload, family="MARKET", value=0.1, count=9):
    payload = deepcopy(fixture_payload["shift_request"])
    payload["observations"][0]["family"] = family
    payload["observations"][0]["value"] = value
    payload["prior_states"][0]["count"] = count
    return ShiftMonitorRequest.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("family,expected", [
    ("RISK", ShiftState.TAIL_SHIFT),
    ("LIQUIDITY", ShiftState.LIQUIDITY_SHIFT),
    ("EXECUTION", ShiftState.EXECUTION_MODEL_SHIFT),
    ("MARKET", ShiftState.MATERIAL_SHIFT),
    ("MODEL", ShiftState.MATERIAL_SHIFT),
])
def test_material_shift_by_family(fixture_payload, family, expected):
    result = run_shift_monitor(_request(fixture_payload, family=family, value=10.0))
    assert result.overall_state is expected


@pytest.mark.parametrize("value", [-0.2, 0.0, 0.2])
def test_normal_values(fixture_payload, value):
    result = run_shift_monitor(_request(fixture_payload, value=value))
    assert result.overall_state is ShiftState.IN_DISTRIBUTION


def test_insufficient_history_degrades(fixture_payload):
    result = run_shift_monitor(_request(fixture_payload, value=0.0, count=0))
    assert result.overall_state is ShiftState.MONITOR_DEGRADED


def test_stale_observation_degrades(fixture_payload):
    payload = deepcopy(fixture_payload["shift_request"])
    payload["observations"][0]["observed_at"] = "2026-08-03T17:00:00Z"
    payload["prior_states"] = []
    result = run_shift_monitor(ShiftMonitorRequest.model_validate_json(json.dumps(payload)))
    assert result.overall_state is ShiftState.MONITOR_DEGRADED


def test_non_advancing_observation_rejected(fixture_payload):
    payload = deepcopy(fixture_payload["shift_request"])
    payload["observations"][0]["observed_at"] = payload["prior_states"][0]["last_observed_at"]
    with pytest.raises(ValueError, match="advance"):
        run_shift_monitor(ShiftMonitorRequest.model_validate_json(json.dumps(payload)))


def test_duplicate_observation_rejected(fixture_payload):
    payload = deepcopy(fixture_payload["shift_request"])
    payload["observations"].append(deepcopy(payload["observations"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        run_shift_monitor(ShiftMonitorRequest.model_validate_json(json.dumps(payload)))


def test_duplicate_prior_state_rejected(fixture_payload):
    payload = deepcopy(fixture_payload["shift_request"])
    payload["prior_states"].append(deepcopy(payload["prior_states"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        run_shift_monitor(ShiftMonitorRequest.model_validate_json(json.dumps(payload)))


def test_state_is_serializable(fixture_payload):
    first = run_shift_monitor(_request(fixture_payload, value=1.0))
    assert first.next_states[0].model_dump_json()
