from __future__ import annotations

from datetime import UTC, datetime

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.evidence.overlay import build_tool_evidence_overlay
from quant_pipeline.phase_03_agents_rag_memory.runtime.tooling import validate_tool_results
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    ArtifactStatus,
    LineageRecord,
    Phase3RunSnapshot,
    RawToolResultPanel,
    RawToolResultRecord,
    RetrievalEvidenceMap,
    ToolCallAuditPanel,
    ToolCallAuditRecord,
    ToolExecutionStatus,
    ToolResultValidationStatus,
    ExecutionMode,
)


def lineage(module: str) -> LineageRecord:
    return LineageRecord(lineage_id=f"{module}:lineage", producer_module_id=module)


def test_tool_evidence_overlay_makes_external_evidence_known_to_s21_validator():
    decision = datetime(2024, 1, 10, tzinfo=UTC)
    evidence = {
        "evidence_id": "ev-1",
        "source_id": "fixture-market",
        "p2_artifact_id": "market-artifact",
        "p2_record_id": "row-1",
        "available_at": "2024-01-09T00:00:00Z",
        "content_hash": "a" * 64,
        "source_quality": 0.9,
    }
    payload = {
        "tool_id": "quant.diagnostics.v1",
        "operation_id": "return_statistics",
        "requested_mode": "BASIC",
        "executed_mode": "BASIC",
        "outcome_status": "PASS",
        "metrics": {"mean": 0.01},
        "evidence_refs": [evidence],
        "coverage": {
            "score": 1.0,
            "observations_requested": 1,
            "observations_used": 1,
            "observations_rejected_future": 0,
            "observations_rejected_quality": 0,
            "missing_requirements": [],
        },
        "latest_available_at": "2024-01-09T00:00:00Z",
        "reason_codes": [],
    }
    raw = RawToolResultRecord(
        tool_call_request_id="req-1",
        cognition_transaction_id="tx-1",
        execution_id="exec-1",
        person_id="person-1",
        tool_id="quant.diagnostics.v1",
        operation_id="return_statistics",
        provider_id="internal_research",
        status=ToolExecutionStatus.SUCCEEDED,
        started_at=decision,
        finished_at=decision,
        available_at=datetime(2024, 1, 9, tzinfo=UTC),
        latency_ms=1.0,
        cost_units=1.0,
        canonical_payload=payload,
        response_hash="b" * 64,
        evidence_refs=("ev-1",),
        result_schema={"type": "object"},
    )
    audit = ToolCallAuditRecord(
        audit_id="audit-1",
        tool_call_request_id="req-1",
        execution_id="exec-1",
        cognition_transaction_id="tx-1",
        person_id="person-1",
        provider_id="internal_research",
        tool_id="quant.diagnostics.v1",
        operation_id="return_statistics",
        status=ToolExecutionStatus.SUCCEEDED,
        started_at=decision,
        finished_at=decision,
        latency_ms=1.0,
        cost_units=1.0,
        retry_count=0,
        request_hash="c" * 64,
        response_hash="b" * 64,
        credential_handle_used=False,
    )
    raw_panel = RawToolResultPanel(status=ArtifactStatus.READY, records=(raw,), lineage=lineage("P3.S21.M03"))
    audit_panel = ToolCallAuditPanel(status=ArtifactStatus.READY, records=(audit,), lineage=lineage("P3.S21.M03"))
    original = RetrievalEvidenceMap(status=ArtifactStatus.EMPTY_VALID, records=(), lineage=lineage("P3.S20.M05"))
    outputs = build_tool_evidence_overlay(
        raw_results=raw_panel,
        audit_panel=audit_panel,
        retrieval_evidence=original,
        decision_time=decision,
    )
    extended = outputs["extended_retrieval_evidence_map"]
    assert {item.evidence_id for item in extended.records} == {"ev-1"}
    validated = validate_tool_results(
        raw_results=raw_panel,
        audit_panel=audit_panel,
        snapshot=Phase3RunSnapshot(
            run_id="run-1",
            cycle_id="cycle-1",
            snapshot_id="snapshot-1",
            as_of=decision,
            execution_mode=ExecutionMode.REPLAY,
            configuration_hash="d" * 64,
        ),
        retrieval_evidence=extended,
    )
    assert validated.records[0].validation_status is ToolResultValidationStatus.VALID
