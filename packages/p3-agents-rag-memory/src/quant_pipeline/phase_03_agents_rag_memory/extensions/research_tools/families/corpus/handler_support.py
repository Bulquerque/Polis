from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import JsonValue, ValidationError

from .canonical import content_hash
from .errors import CorpusToolError, ErrorCategory, error
from .models import (
    CorpusEvidenceRef,
    CorpusMode,
    CorpusToolCallContext,
    CorpusToolResultEnvelope,
    CoverageReport,
    ExecutionReport,
    OutcomeStatus,
    PitQueryProof,
    TimelineEvent,
)
from .retrieval import RetrievalResult, VisibleSelection


def validate_request(model: type[Any], arguments: Mapping[str, JsonValue]) -> Any:
    try:
        return model.model_validate(dict(arguments), strict=False)
    except ValidationError as exc:
        raise CorpusToolError(
            error(
                "P3_RT_CONTRACT_SCHEMA_INVALID",
                ErrorCategory.CONTRACT,
                "corpus tool request does not match its operation schema",
                context={"errors": exc.errors(include_input=False)},
            )
        ) from exc


def retrieval_outcome(result: RetrievalResult) -> OutcomeStatus:
    if not result.hits:
        return OutcomeStatus.EMPTY_VALID
    if result.downgrade_reason or result.coverage.missing_dimensions:
        return OutcomeStatus.DEGRADED
    return OutcomeStatus.PASS


def evidence_from_item(item: Any) -> CorpusEvidenceRef:
    return CorpusEvidenceRef(
        evidence_id=f"evidence_{item.chunk_id}",
        source_id=item.source_id,
        document_id=item.document_id,
        chunk_id=item.chunk_id,
        available_at=item.available_at,
        content_hash=item.content_hash,
        source_quality=item.source_quality,
        lineage_refs=item.lineage_refs,
    )


def evidence_from_items(items: Sequence[Any]) -> tuple[CorpusEvidenceRef, ...]:
    return tuple(evidence_from_item(item) for item in items)


def simple_coverage(selection: VisibleSelection, *, returned: int) -> CoverageReport:
    chunks = selection.chunks
    diagnostics = selection.diagnostics
    return CoverageReport(
        records_scanned=diagnostics.records_scanned,
        records_visible=diagnostics.records_visible,
        records_returned=returned,
        unique_documents=len({item.document_id for item in chunks}),
        unique_sources=len({item.source_id for item in chunks}),
        source_families=len({item.source_id for item in chunks}),
        duplicate_records_removed=diagnostics.duplicate_records_removed,
        score=1.0 if returned else 0.0,
        truncated=False,
    )


def combined_coverage(
    results: Sequence[RetrievalResult],
    *,
    returned: int,
    subqueries: int,
) -> CoverageReport:
    if not results:
        return CoverageReport(
            records_scanned=0,
            records_visible=0,
            records_returned=0,
            unique_documents=0,
            unique_sources=0,
            source_families=0,
            duplicate_records_removed=0,
            score=0.0,
        )
    hits = [hit for result in results for hit in result.hits]
    return CoverageReport(
        records_scanned=max(item.coverage.records_scanned for item in results),
        records_visible=max(item.coverage.records_visible for item in results),
        records_returned=returned,
        unique_documents=len({hit.document_id for hit in hits}),
        unique_sources=len({hit.source_id for hit in hits}),
        source_families=len({hit.source_id for hit in hits}),
        duplicate_records_removed=sum(
            item.coverage.duplicate_records_removed for item in results
        ),
        score=min(1.0, sum(item.coverage.score for item in results) / max(subqueries, 1)),
        missing_dimensions=tuple(
            sorted({value for item in results for value in item.coverage.missing_dimensions})
        ),
        truncated=any(item.coverage.truncated for item in results),
    )


def timeline_events(chunks: Sequence[Any], limit: int) -> tuple[TimelineEvent, ...]:
    by_document: dict[str, list[Any]] = {}
    for chunk in chunks:
        by_document.setdefault(chunk.document_id, []).append(chunk)
    events = [_timeline_event(document_id, items) for document_id, items in by_document.items()]
    return tuple(
        sorted(
            events,
            key=lambda item: (
                item.event_time or item.published_or_reference_time or item.available_at,
                item.document_id,
            ),
        )[:limit]
    )


def _timeline_event(document_id: str, items: Sequence[Any]) -> TimelineEvent:
    ordered = sorted(items, key=lambda item: item.sequence_number)
    first = ordered[0]
    event_times = [item.event_time for item in ordered if item.event_time is not None]
    effective_times = [item.effective_time for item in ordered if item.effective_time is not None]
    summary = " ".join(item.content for item in ordered)[:500].strip() or document_id
    return TimelineEvent(
        event_id=f"timeline_{content_hash({'document_id': document_id})[:24]}",
        document_id=document_id,
        source_id=first.source_id,
        event_time=min(event_times) if event_times else None,
        published_or_reference_time=min(effective_times) if effective_times else None,
        available_at=max(item.available_at for item in ordered),
        summary=summary,
        evidence_chunk_ids=tuple(item.chunk_id for item in ordered),
    )


def empty_proof(context: CorpusToolCallContext) -> PitQueryProof:
    base = {
        "decision_time": context.decision_time,
        "records_scanned": 0,
        "records_visible": 0,
        "records_rejected_future": 0,
        "records_rejected_filter": 0,
        "earliest_available_at": None,
        "latest_available_at": None,
        "snapshot_id": context.snapshot_id,
        "input_hashes": (),
    }
    return PitQueryProof(proof_hash=content_hash(base), **base)


def build_envelope(
    *,
    operation_id: str,
    context: CorpusToolCallContext,
    requested_mode: CorpusMode,
    executed_mode: CorpusMode,
    downgrade_reason: str | None,
    outcome_status: OutcomeStatus,
    records: tuple[dict[str, JsonValue], ...],
    evidence_refs: tuple[CorpusEvidenceRef, ...],
    coverage: CoverageReport,
    pit_proof: PitQueryProof,
    internal_subqueries: int,
    internal_work_units: int,
    warnings: tuple[str, ...],
    provenance: Any | None = None,
) -> CorpusToolResultEnvelope:
    execution = ExecutionReport(
        handler_id=f"p3.s35.{operation_id}",
        handler_version="1.0.0",
        requested_mode=requested_mode,
        executed_mode=executed_mode,
        internal_subqueries=internal_subqueries,
        internal_work_units=internal_work_units,
        deterministic=True,
        seed=context.deterministic_seed,
        warnings=warnings,
    )
    base = {
        "operation_id": operation_id,
        "request_id": context.request_id,
        "outcome_status": outcome_status,
        "requested_mode": requested_mode,
        "executed_mode": executed_mode,
        "downgrade_reason": downgrade_reason,
        "records": records,
        "evidence_refs": evidence_refs,
        "coverage": coverage,
        "provenance": provenance,
        "pit_proof": pit_proof,
        "execution": execution,
    }
    return CorpusToolResultEnvelope(result_hash=content_hash(base), **base)
