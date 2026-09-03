"""Research-process metrics derived from validated S21 tool executions."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from statistics import fmean

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    Phase3RunSnapshot, ToolCallAuditPanel, ToolResultValidationStatus,
    ValidatedToolResultPanel,
)

from ..runtime.models import ResearchProcessPanel, ResearchProcessRecord, ResearchToolResultEnvelope, ResearchToolResultEnvelopePanel, S40Lineage


def _belief_refs(panel: object) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    subjects: dict[str, set[str]] = defaultdict(set)
    propositions: dict[str, set[str]] = defaultdict(set)
    records = panel.get("records", ()) if isinstance(panel, Mapping) else getattr(panel, "records", ())
    for raw in records if isinstance(records, (tuple, list)) else ():
        item = raw if isinstance(raw, Mapping) else getattr(raw, "model_dump", lambda **_: {})()
        tx = item.get("cognition_transaction_id")
        if not isinstance(tx, str):
            continue
        subject, proposition = item.get("underlying_id") or item.get("subject_id"), item.get("proposition_id")
        if isinstance(subject, str) and subject:
            subjects[tx].add(subject)
        if isinstance(proposition, str) and proposition:
            propositions[tx].add(proposition)
    return subjects, propositions


def build_research_process_panel(
    *, validated_results: ValidatedToolResultPanel, audit_panel: ToolCallAuditPanel,
    envelopes: ResearchToolResultEnvelopePanel, phase3_snapshot: Phase3RunSnapshot,
    belief_panel: object | None = None,
) -> ResearchProcessPanel:
    grouped = _valid_envelopes(validated_results, envelopes)
    subjects, propositions = _belief_refs(belief_panel or {})
    records = tuple(
        _process_record(tx, grouped[tx], phase3_snapshot, subjects, propositions)
        for tx in sorted(grouped)
    )
    source_hashes = {
        "validated_tool_result_panel": content_hash(validated_results.model_dump(mode="json")),
        "tool_call_audit_panel": content_hash(audit_panel.model_dump(mode="json")),
        "research_tool_result_envelope_panel": envelopes.panel_hash,
    }
    lineage = S40Lineage(
        lineage_id=f"P3.S40.M06:{content_hash(source_hashes)[:20]}",
        producer_module_id="P3.S40.M06",
        source_artifact_ids=tuple(source_hashes),
        source_hashes=source_hashes,
        transformation_ids=("p3.s40.research.process.v1",),
    )
    body = {"records": records, "lineage": lineage}
    return ResearchProcessPanel(**body, panel_hash=content_hash(body))


def _valid_envelopes(validated_results, envelopes):
    by_execution = {item.execution_id: item for item in envelopes.records}
    valid = {
        item.raw_result.execution_id for item in validated_results.records
        if item.validation_status is ToolResultValidationStatus.VALID
    }
    grouped: dict[str, list[ResearchToolResultEnvelope]] = defaultdict(list)
    for execution_id in sorted(valid):
        envelope = by_execution.get(execution_id)
        if envelope is not None:
            grouped[envelope.cognition_transaction_id].append(envelope)
    return grouped


def _process_record(transaction_id, group, snapshot, subjects, propositions):
    ordered = sorted(group, key=lambda item: item.execution_id)
    qualities = [item.source_quality for envelope in ordered for item in envelope.provenance.evidence]
    latest = [envelope.pit_proof.latest_available_at for envelope in ordered if envelope.pit_proof.latest_available_at]
    latency = max(0.0, (snapshot.as_of - max(latest)).total_seconds()) if latest else 0.0
    operation_keys = tuple(f"{item.tool_id}/{item.operation_id}" for item in ordered)
    body = {
        "process_id": f"research-process:{content_hash([snapshot.run_id, transaction_id])[:20]}",
        "run_id": snapshot.run_id,
        "cycle_id": snapshot.cycle_id,
        "cognition_transaction_id": transaction_id,
        "person_id": ordered[0].person_id,
        "subject_refs": tuple(sorted(subjects.get(transaction_id, set()))),
        "proposition_refs": tuple(sorted(propositions.get(transaction_id, set()))),
        "tool_families_used": tuple(sorted({item.tool_id for item in ordered})),
        "operations_used": tuple(sorted({item.operation_id for item in ordered})),
        "operation_keys": operation_keys,
        "requested_modes": tuple(item.requested_mode for item in ordered),
        "executed_modes": tuple(item.executed_mode for item in ordered),
        "visible_tool_call_count": len(ordered),
        "internal_subquery_count": 0,
        "cost_units": sum(item.execution.cost_units for item in ordered),
        "source_diversity": len({item.source_id for envelope in ordered for item in envelope.provenance.evidence}),
        "source_quality_mean": fmean(qualities) if qualities else 1.0,
        "evidence_coverage": fmean([item.coverage.score for item in ordered]) if ordered else 0.0,
        "counterevidence_ratio": 0.0,
        "information_latency_seconds": latency,
        "future_records_rejected": sum(item.pit_proof.records_rejected_future for item in ordered),
        "downgrade_count": sum(item.requested_mode != item.executed_mode for item in ordered),
        "truncated": any("TRUNCATED" in code for item in ordered for code in item.reason_codes),
        "evidence_refs": tuple(sorted({ref for item in ordered for ref in item.evidence_refs})),
    }
    return ResearchProcessRecord(**body, process_hash=content_hash(body))
