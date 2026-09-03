from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S29_M01_agent_disagreement_panel_builder import (
    IMPLEMENTED,
    MODULE_ID,
    run_module,
)
from quant_pipeline.phase_03_agents_rag_memory.s29_products import S29ContractError


def _output(result: dict) -> dict:
    return result["outputs"]["agent_disagreement_panel"]


def test_module_identity_and_implementation_flag() -> None:
    assert MODULE_ID == "P3.S29.M01"
    assert IMPLEMENTED is True


def test_valid_fixture_materializes_two_records(m01_inputs: dict, execution_context: dict) -> None:
    result = run_module(m01_inputs, execution_context)
    output = _output(result)
    assert output["quality_status"] == "PASS"
    assert len(output["records"]) == 2
    assert result["implementation_status"] == "IMPLEMENTED_QUALIFIED_INTERNAL"
    assert result["observability"]["output_record_count"] == 2


def test_consensus_has_zero_disagreement(m01_inputs: dict, execution_context: dict) -> None:
    output = _output(run_module(m01_inputs, execution_context))
    record = next(item for item in output["records"] if item["underlying"] == "VALE3")
    assert record["disagreement_score"] == 0.0
    assert record["agent_agreement_score"] == 1.0


def test_composite_formula_matches_declared_components(m01_inputs: dict, execution_context: dict) -> None:
    output = _output(run_module(m01_inputs, execution_context))
    record = next(item for item in output["records"] if item["underlying"] == "PETR4")
    expected = (
        0.30 * 0.946394630357
        + 0.20 * 0.36
        + 0.20 * 0.40
        + 0.15 * 0.35
        + 0.15 * 0.72
    )
    assert record["disagreement_score"] == round(expected, 12)
    assert record["agent_agreement_score"] == round(1.0 - expected, 12)


def test_low_coverage_is_blocked_not_zero(m01_inputs: dict, execution_context: dict) -> None:
    m01_inputs["belief_distribution_panel"]["records"][0]["coverage_ratio"] = 0.2
    output = _output(run_module(m01_inputs, execution_context))
    record = next(item for item in output["records"] if item["underlying"] == "PETR4")
    assert record["quality_status"] == "BLOCKED"
    assert record["disagreement_score"] is None
    assert record["agent_agreement_score"] is None
    assert "COVERAGE_BELOW_MINIMUM" in record["quality_reasons"]


def test_low_source_quality_is_degraded(m01_inputs: dict, execution_context: dict) -> None:
    m01_inputs["belief_distribution_panel"]["records"][0]["source_quality_score"] = 0.4
    output = _output(run_module(m01_inputs, execution_context))
    record = next(item for item in output["records"] if item["underlying"] == "PETR4")
    assert record["quality_status"] == "DEGRADED"
    assert record["disagreement_score"] is not None


def test_grain_mismatch_fails_closed(m01_inputs: dict, execution_context: dict) -> None:
    m01_inputs["validated_society_state_panel"]["records"][0]["horizon"] = "90d"
    with pytest.raises(S29ContractError, match="grain mismatch"):
        run_module(m01_inputs, execution_context)


def test_duplicate_grain_fails_closed(m01_inputs: dict, execution_context: dict) -> None:
    m01_inputs["belief_distribution_panel"]["records"].append(
        deepcopy(m01_inputs["belief_distribution_panel"]["records"][0])
    )
    with pytest.raises(S29ContractError, match="duplicate belief distribution key"):
        run_module(m01_inputs, execution_context)


def test_invalid_weights_fail_contract(m01_inputs: dict, execution_context: dict) -> None:
    m01_inputs["aggregation_semantics_config"]["weights"]["evidence_diversity"] = 0.20
    with pytest.raises(S29ContractError, match="weights must sum"):
        run_module(m01_inputs, execution_context)


def test_forbidden_field_is_detected_recursively(m01_inputs: dict, execution_context: dict) -> None:
    m01_inputs["belief_distribution_panel"]["records"][0]["nested"] = {
        "future_return": 0.5
    }
    with pytest.raises(S29ContractError, match="forbidden field"):
        run_module(m01_inputs, execution_context)


def test_future_dated_record_fails(m01_inputs: dict, execution_context: dict) -> None:
    future = "2024-02-01T20:00:00Z"
    m01_inputs["belief_distribution_panel"]["records"][0]["as_of_time"] = future
    m01_inputs["validated_society_state_panel"]["records"][0]["as_of_time"] = future
    with pytest.raises(S29ContractError, match="as_of_time"):
        run_module(m01_inputs, execution_context)


def test_record_order_does_not_change_artifact(m01_inputs: dict, execution_context: dict) -> None:
    first = _output(run_module(m01_inputs, execution_context))
    reversed_inputs = deepcopy(m01_inputs)
    reversed_inputs["belief_distribution_panel"]["records"].reverse()
    reversed_inputs["validated_society_state_panel"]["records"].reverse()
    second = _output(run_module(reversed_inputs, execution_context))
    assert first == second


def test_output_preserves_p4_legacy_metadata(m01_inputs: dict, execution_context: dict) -> None:
    output = _output(run_module(m01_inputs, execution_context))
    for field in ("artifact_id", "created_at", "lineage_id", "pipeline_version"):
        assert output[field]
    assert isinstance(output["records"], list)
