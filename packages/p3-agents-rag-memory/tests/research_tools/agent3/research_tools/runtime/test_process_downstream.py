from __future__ import annotations

from datetime import UTC, datetime

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.evidence.downstream import build_p9_learning_evidence
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.models import (
    ConsumerCompatibilityStatus, ResearchProcessPanel, ResearchProcessRecord,
    ResearchToolExecutionTracePanel, S40Lineage,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import ExecutionMode, Phase3RunSnapshot
from quant_pipeline.phase_03_agents_rag_memory.s31_models import CutoffRiskClass, ModelKnowledgeCutoffReport


def lineage(module: str) -> S40Lineage:
    return S40Lineage(lineage_id=f"{module}:lineage", producer_module_id=module)


def test_p9_learning_records_keep_aligned_tool_operation_pairs():
    body = {
        "process_id": "process-1", "run_id": "run-1", "cycle_id": "cycle-1",
        "cognition_transaction_id": "tx-1", "person_id": "person-1",
        "tool_families_used": ("macro.observation.v1", "quant.diagnostics.v1"),
        "operations_used": ("get_observations", "return_statistics"),
        "operation_keys": ("quant.diagnostics.v1/return_statistics", "macro.observation.v1/get_observations"),
        "requested_modes": ("BASIC", "LOOKUP"), "executed_modes": ("BASIC", "LOOKUP"),
        "visible_tool_call_count": 2, "cost_units": 3.0, "source_diversity": 2,
        "source_quality_mean": 0.9, "evidence_coverage": 0.8,
        "information_latency_seconds": 1.0, "future_records_rejected": 0,
        "downgrade_count": 0, "truncated": False, "evidence_refs": ("ev-1",),
    }
    record = ResearchProcessRecord(**body, process_hash=content_hash(body))
    panel_body = {"records": (record,), "lineage": lineage("P3.S40.M06")}
    panel = ResearchProcessPanel(**panel_body, panel_hash=content_hash(panel_body))
    trace_body = {"records": (), "lineage": lineage("P3.S40.M04")}
    traces = ResearchToolExecutionTracePanel(**trace_body, panel_hash=content_hash(trace_body))
    snapshot = Phase3RunSnapshot(
        run_id="run-1", cycle_id="cycle-1", snapshot_id="snapshot-1",
        as_of=datetime(2024, 1, 10, tzinfo=UTC), execution_mode=ExecutionMode.REPLAY,
        configuration_hash="a" * 64,
    )
    cutoff = ModelKnowledgeCutoffReport(
        provider_id="fixture", model_id="fixture", model_version="v1",
        known_training_cutoff=datetime(2023, 1, 1, tzinfo=UTC).date(),
        evaluation_start=datetime(2024, 1, 1, tzinfo=UTC),
        evaluation_end=datetime(2024, 1, 31, tzinfo=UTC),
        risk_class=CutoffRiskClass.STRICT_CLEAN, rationale="fixture", lineage_id="cutoff:fixture",
    )
    commitments = {"records": ({"cognition_transaction_id": "tx-1", "commitment_id": "commit-1"},)}
    bundle, handoff, report = build_p9_learning_evidence(
        process_panel=panel, trace_panel=traces, phase3_snapshot=snapshot,
        model_knowledge_cutoff=cutoff, belief_commitment_panel=commitments,
    )
    assert [(item.tool_id, item.operation_id) for item in bundle.records] == [
        ("quant.diagnostics.v1", "return_statistics"),
        ("macro.observation.v1", "get_observations"),
    ]
    assert handoff.compatibility_status is ConsumerCompatibilityStatus.DEFERRED_BY_GOVERNANCE
    assert report["governance_deferred"] is True
    assert report["feedback_timing"] == "N_PLUS_1_ONLY"
