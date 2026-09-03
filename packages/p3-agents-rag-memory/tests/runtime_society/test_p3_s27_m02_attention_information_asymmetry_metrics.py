from __future__ import annotations

from copy import deepcopy
import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S27_M02_attention_information_asymmetry_metrics import run_module
from quant_pipeline.phase_03_agents_rag_memory.s27.errors import S27ContractError, S27TemporalError
from s27_test_support import m02_inputs


def test_golden_fixture_exact() -> None:
    record = run_module(m02_inputs())["attention_information_metrics"]["records"][0]
    assert record["status"] == "READY"
    assert record["attention_intensity"] == pytest.approx(0.375)
    assert record["attention_concentration"] == pytest.approx(0.029049405545331197)
    assert record["mean_information_access_score"] == pytest.approx(0.28)
    assert record["information_asymmetry"] == pytest.approx(0.2515949125081825)
    assert record["entitlement_coverage_ratio"] == pytest.approx(0.75)
    assert record["executed_tool_coverage_ratio"] == pytest.approx(0.25)
    assert record["validated_tool_call_count"] == 1


def test_authorized_unexecuted_tool_is_excluded() -> None:
    inputs = m02_inputs()
    inputs["tool_call_audit_panel"]["records"][1]["information_gain"] = 1.0
    result = run_module(inputs)["attention_information_metrics"]["records"][0]
    assert result["validated_tool_call_count"] == 1
    assert result["executed_tool_coverage_ratio"] == pytest.approx(0.25)


def test_no_emergence_state_produces_no_records_when_no_tool_groups() -> None:
    inputs = m02_inputs()
    for person in inputs["validated_next_person_state_panel"]["records"]:
        person["emergence_states"] = []
    inputs["tool_call_audit_panel"]["records"] = []
    result = run_module(inputs)["attention_information_metrics"]
    assert result["records"] == []


def test_duplicate_person_group_fails() -> None:
    inputs = m02_inputs()
    state = deepcopy(inputs["validated_next_person_state_panel"]["records"][0]["emergence_states"][0])
    inputs["validated_next_person_state_panel"]["records"][0]["emergence_states"].append(state)
    with pytest.raises(S27ContractError, match="duplicate emergence state"):
        run_module(inputs)


def test_context_mismatch_fails() -> None:
    inputs = m02_inputs()
    inputs["tool_call_audit_panel"]["cycle_id"] = 8
    with pytest.raises(S27ContractError, match="context mismatch"):
        run_module(inputs)


def test_future_tool_call_fails() -> None:
    inputs = m02_inputs()
    inputs["tool_call_audit_panel"]["records"][0]["executed_at"] = "2026-06-11T00:00:00Z"
    with pytest.raises(S27TemporalError):
        run_module(inputs)


def test_order_independent() -> None:
    inputs = m02_inputs()
    reordered = deepcopy(inputs)
    reordered["validated_next_person_state_panel"]["records"].reverse()
    reordered["tool_call_audit_panel"]["records"].reverse()
    assert run_module(inputs) == run_module(reordered)
