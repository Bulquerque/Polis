import json
from copy import deepcopy

import pytest

from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.enums import AlertSeverity, ReasonCode
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.invariant_monitor import run_invariant_monitor
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.models_invariants import InvariantMonitorRequest


def _run(fixture_payload, field=None, value=None):
    payload = deepcopy(fixture_payload["invariant_request"])
    if field is not None:
        payload["snapshot"][field] = value
    return run_invariant_monitor(InvariantMonitorRequest.model_validate_json(json.dumps(payload)))


def test_healthy_snapshot(fixture_payload):
    result = _run(fixture_payload)
    assert result.healthy
    assert result.highest_severity is AlertSeverity.INFO


@pytest.mark.parametrize("field,value,code", [
    ("terminal_candidate_count", 1, ReasonCode.CANDIDATE_CONSERVATION_FAIL),
    ("open_quantity", "1", ReasonCode.ORDER_CONSERVATION_FAIL),
    ("physical_allocated_total", "99", ReasonCode.DUAL_BOOK_RECONCILIATION_FAIL),
    ("closing_cash", "989", ReasonCode.CASH_RECONCILIATION_FAIL),
    ("maximum_loss", "201", ReasonCode.MAX_LOSS_BREACH),
    ("quote_age_seconds", 61, ReasonCode.QUOTE_STALE),
    ("lifecycle_consistent", False, ReasonCode.LIFECYCLE_INCONSISTENT),
    ("settlement_consistent", False, ReasonCode.SETTLEMENT_INCONSISTENT),
    ("actual_state_hash", "b"*64, ReasonCode.STATE_HASH_MISMATCH),
])
def test_detects_invariant_failures(fixture_payload, field, value, code):
    result = _run(fixture_payload, field, value)
    assert code in {item.reason_code for item in result.violations}


@pytest.mark.parametrize("margin_used,severity", [("950", AlertSeverity.MATERIAL), ("1100", AlertSeverity.CRITICAL)])
def test_margin_severity(fixture_payload, margin_used, severity):
    result = _run(fixture_payload, "margin_used", margin_used)
    violation = next(v for v in result.violations if v.reason_code is ReasonCode.MARGIN_HEADROOM_BREACH)
    assert violation.severity is severity


def test_violations_sorted(fixture_payload):
    payload = deepcopy(fixture_payload["invariant_request"])
    payload["snapshot"]["closing_cash"] = "0"
    payload["snapshot"]["terminal_candidate_count"] = 0
    result = run_invariant_monitor(InvariantMonitorRequest.model_validate_json(json.dumps(payload)))
    assert [v.invariant_id for v in result.violations] == sorted(v.invariant_id for v in result.violations)
