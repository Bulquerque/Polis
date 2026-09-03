"""Evidence-map overlay inserted between P3.S21.M03 and P3.S21.M04."""
from __future__ import annotations

from datetime import datetime

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    ArtifactStatus, EvidenceRef, LineageRecord, RawToolResultPanel,
    RetrievalEvidenceMap, ToolCallAuditPanel,
)

from ..runtime.models import (
    ProvenanceEvidence, ResearchToolEvidenceMap, ResearchToolExecutionTracePanel,
    ResearchToolExecutionTraceRecord, ResearchToolResultEnvelope,
    ResearchToolResultEnvelopePanel, S40Lineage,
)
from .envelope import build_result_envelope


def _lineage(source_hashes: dict[str, str]) -> S40Lineage:
    return S40Lineage(
        lineage_id=f"P3.S40.M04:{content_hash(source_hashes)[:20]}",
        producer_module_id="P3.S40.M04",
        source_artifact_ids=tuple(source_hashes),
        source_hashes=source_hashes,
        transformation_ids=("p3.s40.evidence.overlay.v1",),
    )


def _merge_evidence(existing: RetrievalEvidenceMap, added: tuple[ProvenanceEvidence, ...]) -> tuple[EvidenceRef, ...]:
    records = {item.evidence_id: item for item in existing.records}
    for item in added:
        projected = EvidenceRef(
            evidence_id=item.evidence_id, source_id=item.source_id,
            available_at=item.available_at, content_hash=item.content_hash,
            source_quality=item.source_quality,
        )
        prior = records.get(projected.evidence_id)
        if prior is not None and prior != projected:
            raise ValueError(f"evidence overlay conflicts with existing evidence: {projected.evidence_id}")
        records[projected.evidence_id] = projected
    return tuple(records[key] for key in sorted(records))


def build_tool_evidence_overlay(
    *, raw_results: RawToolResultPanel, audit_panel: ToolCallAuditPanel,
    retrieval_evidence: RetrievalEvidenceMap, decision_time: datetime,
) -> dict[str, object]:
    audits = {item.execution_id: item for item in audit_panel.records}
    envelopes, provenance, traces = _materialize(raw_results, audits, decision_time)
    source_hashes = _source_hashes(raw_results, audit_panel, retrieval_evidence)
    lineage = _lineage(source_hashes)
    envelope_panel = _envelope_panel(envelopes, lineage)
    evidence_map = _evidence_map(provenance, lineage)
    trace_panel = _trace_panel(traces, lineage)
    extended = _extended_map(retrieval_evidence, tuple(provenance.values()), evidence_map, source_hashes, lineage)
    return {
        "research_tool_result_envelope_panel": envelope_panel,
        "research_tool_evidence_map": evidence_map,
        "extended_retrieval_evidence_map": extended,
        "research_tool_execution_trace_panel": trace_panel,
    }


def _materialize(raw_results, audits, decision_time):
    envelopes: list[ResearchToolResultEnvelope] = []
    provenance: dict[str, ProvenanceEvidence] = {}
    traces: list[ResearchToolExecutionTraceRecord] = []
    for result in sorted(raw_results.records, key=lambda item: item.execution_id):
        audit = audits.get(result.execution_id)
        envelope = build_result_envelope(result=result, audit=audit, decision_time=decision_time) if audit else None
        if envelope is None:
            continue
        envelopes.append(envelope)
        _add_provenance(provenance, envelope.provenance.evidence)
        traces.append(_trace(envelope, result.finished_at))
    return tuple(envelopes), provenance, tuple(traces)


def _add_provenance(target: dict[str, ProvenanceEvidence], evidence: tuple[ProvenanceEvidence, ...]) -> None:
    for item in evidence:
        prior = target.get(item.evidence_id)
        if prior is not None and prior != item:
            raise ValueError(f"conflicting tool evidence: {item.evidence_id}")
        target[item.evidence_id] = item


def _trace(envelope: ResearchToolResultEnvelope, event_time: datetime) -> ResearchToolExecutionTraceRecord:
    body = {
        "trace_id": envelope.execution.trace_id,
        "span_id": content_hash({"trace": envelope.execution.trace_id, "event": "evidence"})[:16],
        "event_name": "tool.evidence.materialized",
        "event_time": event_time,
        "cognition_transaction_id": envelope.cognition_transaction_id,
        "request_id": envelope.request_id,
        "execution_id": envelope.execution_id,
        "tool_id": envelope.tool_id,
        "operation_id": envelope.operation_id,
        "attributes": {
            "evidence_count": len(envelope.provenance.evidence),
            "outcome_status": envelope.outcome_status.value,
            "future_records_rejected": envelope.pit_proof.records_rejected_future,
        },
    }
    return ResearchToolExecutionTraceRecord(**body, event_hash=content_hash(body))


def _source_hashes(raw_results, audit_panel, retrieval_evidence) -> dict[str, str]:
    return {
        "raw_tool_result_panel": content_hash(raw_results.model_dump(mode="json")),
        "tool_call_audit_panel": content_hash(audit_panel.model_dump(mode="json")),
        "retrieval_evidence_map": content_hash(retrieval_evidence.model_dump(mode="json")),
    }


def _envelope_panel(records, lineage):
    body = {"records": records, "lineage": lineage}
    return ResearchToolResultEnvelopePanel(**body, panel_hash=content_hash(body))


def _evidence_map(records, lineage):
    body = {"records": tuple(records[key] for key in sorted(records)), "lineage": lineage}
    return ResearchToolEvidenceMap(**body, map_hash=content_hash(body))


def _trace_panel(records, lineage):
    body = {"records": records, "lineage": lineage}
    return ResearchToolExecutionTracePanel(**body, panel_hash=content_hash(body))


def _extended_map(existing, added, evidence_map, source_hashes, lineage):
    combined = _merge_evidence(existing, added)
    return RetrievalEvidenceMap(
        status=ArtifactStatus.READY if combined else ArtifactStatus.EMPTY_VALID,
        records=combined,
        lineage=LineageRecord(
            lineage_id=f"P3.S40.M04:{content_hash([item.evidence_id for item in combined])[:20]}",
            source_artifact_ids=(existing.lineage.lineage_id, lineage.lineage_id),
            source_hashes={
                existing.lineage.lineage_id: source_hashes["retrieval_evidence_map"],
                lineage.lineage_id: evidence_map.map_hash,
            },
            producer_module_id="P3.S40.M04",
        ),
        reason_code=None if combined else "NO_RETRIEVAL_OR_TOOL_EVIDENCE",
    )
