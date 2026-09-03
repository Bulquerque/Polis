from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S29_M02_evidence_claim_extractor import (
    IMPLEMENTED,
    MODULE_ID,
    run_module,
)
from quant_pipeline.phase_03_agents_rag_memory.s29_products import (
    S29ContractError,
    S29LineageError,
    S29TemporalError,
)


def _output(result: dict) -> dict:
    return result["outputs"]["evidence_tag_panel"]


def test_module_identity_and_implementation_flag() -> None:
    assert MODULE_ID == "P3.S29.M02"
    assert IMPLEMENTED is True


def test_valid_fixture_materializes_traceability_chain(m02_inputs: dict, execution_context: dict) -> None:
    output = _output(run_module(m02_inputs, execution_context))
    assert output["quality_status"] == "PASS"
    assert len(output["records"]) == 1
    record = output["records"][0]
    assert record["belief_update_id"] == "belief-update-001"
    assert record["claim_id"] == "claim-001"
    assert record["evidence_id"] == "evidence-rag-001"
    assert record["source_id"] == "source-cvm-001"
    assert record["chunk_id"] == "chunk-001"


def test_tag_is_taken_from_structured_claim_type(m02_inputs: dict, execution_context: dict) -> None:
    output = _output(run_module(m02_inputs, execution_context))
    assert output["records"][0]["evidence_tag"] == "fundamentals.earnings"


def test_orphan_claim_fails(m02_inputs: dict, execution_context: dict) -> None:
    m02_inputs["agent_reading_panel"]["records"][0]["belief_update_id"] = "unknown"
    with pytest.raises(S29LineageError, match="orphan claims"):
        run_module(m02_inputs, execution_context)


def test_missing_evidence_fails(m02_inputs: dict, execution_context: dict) -> None:
    m02_inputs["retrieval_evidence_map"]["records"] = []
    with pytest.raises(S29LineageError, match="missing evidence"):
        run_module(m02_inputs, execution_context)


def test_future_evidence_fails(m02_inputs: dict, execution_context: dict) -> None:
    m02_inputs["retrieval_evidence_map"]["records"][0]["available_at"] = (
        "2024-02-01T00:00:00Z"
    )
    with pytest.raises(S29TemporalError, match="after as_of_time"):
        run_module(m02_inputs, execution_context)


def test_rag_index_mismatch_fails(m02_inputs: dict, execution_context: dict) -> None:
    m02_inputs["rag_index_artifact"]["records"][0]["source_id"] = "different-source"
    with pytest.raises(S29LineageError, match="canonical index entry"):
        run_module(m02_inputs, execution_context)


def test_claim_grain_mismatch_fails(m02_inputs: dict, execution_context: dict) -> None:
    m02_inputs["agent_reading_panel"]["records"][0]["horizon"] = "90d"
    with pytest.raises(S29LineageError, match="does not match"):
        run_module(m02_inputs, execution_context)


def test_evidence_binding_mismatch_fails(m02_inputs: dict, execution_context: dict) -> None:
    m02_inputs["evidence_bound_belief_update_panel"]["records"][0][
        "context_evidence_refs"
    ] = ["evidence-unrepresented"]
    with pytest.raises(S29LineageError, match="evidence binding mismatch"):
        run_module(m02_inputs, execution_context)


def test_duplicate_evidence_across_maps_fails(m02_inputs: dict, execution_context: dict) -> None:
    duplicate = deepcopy(m02_inputs["retrieval_evidence_map"]["records"][0])
    duplicate["evidence_kind"] = "GRAPH_PATH"
    duplicate["chunk_id"] = None
    duplicate["graph_path_id"] = "path-001"
    m02_inputs["graph_evidence_map"]["records"] = [duplicate]
    with pytest.raises(S29LineageError, match="multiple evidence maps"):
        run_module(m02_inputs, execution_context)


def test_low_source_quality_is_materialized_as_degraded(m02_inputs: dict, execution_context: dict) -> None:
    m02_inputs["retrieval_evidence_map"]["records"][0]["source_quality_score"] = 0.4
    output = _output(run_module(m02_inputs, execution_context))
    assert output["quality_status"] == "DEGRADED"
    assert output["records"][0]["quality_status"] == "DEGRADED"
    assert "LOW_SOURCE_QUALITY" in output["records"][0]["quality_reasons"]


def test_forbidden_field_is_detected_recursively(m02_inputs: dict, execution_context: dict) -> None:
    m02_inputs["agent_reading_panel"]["records"][0]["metadata"] = {
        "trade_decision": "BUY"
    }
    with pytest.raises(S29ContractError, match="forbidden field"):
        run_module(m02_inputs, execution_context)


def test_output_is_deterministic(m02_inputs: dict, execution_context: dict) -> None:
    first = _output(run_module(m02_inputs, execution_context))
    second = _output(run_module(deepcopy(m02_inputs), deepcopy(execution_context)))
    assert first == second


def test_output_preserves_p4_legacy_metadata(m02_inputs: dict, execution_context: dict) -> None:
    output = _output(run_module(m02_inputs, execution_context))
    for field in ("artifact_id", "created_at", "lineage_id", "pipeline_version"):
        assert output[field]
    assert isinstance(output["records"], list)
