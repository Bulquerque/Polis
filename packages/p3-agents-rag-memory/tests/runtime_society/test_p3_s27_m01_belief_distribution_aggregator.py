from __future__ import annotations

from copy import deepcopy
import math
import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S27_M01_belief_distribution_aggregator import run_module
from quant_pipeline.phase_03_agents_rag_memory.s27.errors import S27ContractError, S27TemporalError
from s27_test_support import m01_inputs


def test_golden_fixture_exact() -> None:
    result = run_module(m01_inputs())["belief_distribution_panel"]
    petr = result["records"][0]
    vale = result["records"][1]
    assert petr["status"] == "DEGRADED"
    assert petr["belief_mean"] == pytest.approx(-0.00714285714285715)
    assert petr["belief_variance"] == pytest.approx(0.19209183673469388)
    assert petr["belief_entropy"] == pytest.approx(0.9952325573220987)
    assert petr["belief_polarization"] == pytest.approx(0.3492063492063492)
    assert petr["effective_n"] == pytest.approx(2.9696969696969693)
    assert petr["belief_reversal_rate"] == 1.0
    assert vale["status"] == "NO_COVERAGE"
    assert vale["belief_mean"] is None


def test_input_order_does_not_change_output() -> None:
    original = m01_inputs()
    reversed_inputs = deepcopy(original)
    reversed_inputs["next_belief_state_panel"]["records"].reverse()
    reversed_inputs["validated_population_manifest"]["records"].reverse()
    assert run_module(original) == run_module(reversed_inputs)


def test_missing_prior_timestamp_degrades_not_invents_velocity() -> None:
    inputs = m01_inputs()
    for record in inputs["next_belief_state_panel"]["records"]:
        record["prior_updated_at"] = None
    record = run_module(inputs)["belief_distribution_panel"]["records"][0]
    assert record["status"] == "DEGRADED"
    assert record["belief_update_velocity_per_day"] is None
    assert record["dynamics_coverage_ratio"] == 0.0


def test_genesis_dynamics_are_explicitly_not_applicable() -> None:
    inputs = m01_inputs()
    for record in inputs["next_belief_state_panel"]["records"]:
        record["prior_updated_at"] = None
        record["prior_value"] = 0.0
        record["delta"] = record["new_value"]
    record = run_module(inputs)["belief_distribution_panel"]["records"][0]
    assert record["status"] == "READY"
    assert record["belief_update_velocity_per_day"] is None
    assert record["belief_reversal_rate"] is None
    assert record["dynamics_applicability"] == "NOT_APPLICABLE_GENESIS"


def test_duplicate_person_group_fails_closed() -> None:
    inputs = m01_inputs()
    inputs["next_belief_state_panel"]["records"].append(deepcopy(inputs["next_belief_state_panel"]["records"][0]))
    with pytest.raises(S27ContractError, match="duplicate belief"):
        run_module(inputs)


def test_unknown_proposition_fails() -> None:
    inputs = m01_inputs()
    inputs["next_belief_state_panel"]["records"][0]["proposition_id"] = "unknown"
    with pytest.raises(S27ContractError, match="unknown proposition"):
        run_module(inputs)


def test_future_belief_fails() -> None:
    inputs = m01_inputs()
    inputs["next_belief_state_panel"]["records"][0]["changed_at"] = "2026-06-11T00:00:00Z"
    with pytest.raises(S27TemporalError):
        run_module(inputs)


def test_forbidden_field_rejected() -> None:
    inputs = m01_inputs()
    inputs["next_belief_state_panel"]["future_return"] = 0.2
    with pytest.raises(S27ContractError, match="forbidden field"):
        run_module(inputs)


def test_shares_sum_to_one_when_covered() -> None:
    record = run_module(m01_inputs())["belief_distribution_panel"]["records"][0]
    assert math.fsum([record["bullish_share"], record["neutral_share"], record["bearish_share"]]) == pytest.approx(1.0)


def test_three_person_decimal_weights_stay_inside_probability_domain() -> None:
    inputs = deepcopy(m01_inputs())
    for record in inputs["validated_population_manifest"]["records"]:
        record["representation_weight"] = 1.0 / 3.0
    record = run_module(inputs)["belief_distribution_panel"]["records"][0]
    assert 0.0 <= record["bullish_share"] <= 1.0
    assert 0.0 <= record["neutral_share"] <= 1.0
    assert 0.0 <= record["bearish_share"] <= 1.0
