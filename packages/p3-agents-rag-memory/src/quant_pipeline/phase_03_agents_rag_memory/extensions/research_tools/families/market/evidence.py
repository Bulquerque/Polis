from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash

from .normalization import parse_datetime, row_hash, stable_id
from .ports import VisibleRecordBatch
from .result_contracts import (
    CoverageReport,
    ExecutionReport,
    MarketDerivativesToolResultEnvelope,
    MarketEvidenceRef,
    PitQueryProof,
)
from .types import OutcomeStatus


def availability_for(view_name: str, row: Mapping[str, object]) -> datetime:
    field = "first_seen_date" if view_name == "clean_option_contract_panel" else "available_at"
    return parse_datetime(row[field], field=field)


def evidence_ref(
    view_name: str,
    row: Mapping[str, object],
    *,
    key_fields: tuple[str, ...],
) -> MarketEvidenceRef:
    available_at = availability_for(view_name, row)
    record_key = "|".join(str(row.get(field) or "") for field in key_fields)
    source_id = str(row.get("source_id") or "UNKNOWN")
    lineage_id = str(row.get("lineage_id") or "UNKNOWN")
    digest = row_hash(row)
    return MarketEvidenceRef(
        evidence_id=stable_id("evidence", view_name, record_key, digest),
        view_name=view_name,
        record_key=record_key,
        source_id=source_id,
        lineage_id=lineage_id,
        available_at=available_at,
        record_hash=digest,
    )


def build_pit_proof(
    batches: Iterable[VisibleRecordBatch],
    *,
    decision_time: datetime,
) -> PitQueryProof:
    materialized = tuple(batches)
    visible_rows = [
        (batch.view_name, row)
        for batch in materialized
        for row in batch.rows
    ]
    times = [availability_for(view_name, row) for view_name, row in visible_rows]
    input_hashes = tuple(sorted({digest for batch in materialized for digest in batch.input_hashes}))
    base = {
        "decision_time": decision_time,
        "records_scanned": sum(batch.records_scanned for batch in materialized),
        "records_visible": len(visible_rows),
        "records_rejected_future": sum(batch.records_rejected_future for batch in materialized),
        "records_rejected_missing_time": sum(
            batch.records_rejected_missing_time for batch in materialized
        ),
        "records_rejected_filter": sum(batch.records_rejected_filter for batch in materialized),
        "earliest_available_at": min(times) if times else None,
        "latest_available_at": max(times) if times else None,
        "snapshot_id": materialized[0].snapshot_id if materialized else "unknown",
        "input_hashes": input_hashes,
    }
    return PitQueryProof(proof_hash=content_hash(base), **base)


def build_coverage(
    batches: Iterable[VisibleRecordBatch],
    *,
    records_returned: int,
    unique_sources: int,
    missing_dimensions: Iterable[str] = (),
    truncated: bool = False,
) -> CoverageReport:
    materialized = tuple(batches)
    visible = sum(len(batch.rows) for batch in materialized)
    missing = tuple(sorted(set(missing_dimensions)))
    if visible == 0:
        score = 0.0
    else:
        completeness = min(1.0, records_returned / max(1, visible))
        dimension_penalty = 1.0 / (1.0 + len(missing))
        score = max(0.0, min(1.0, 0.5 * completeness + 0.5 * dimension_penalty))
    return CoverageReport(
        records_scanned=sum(batch.records_scanned for batch in materialized),
        records_visible=visible,
        records_returned=records_returned,
        records_rejected_future=sum(batch.records_rejected_future for batch in materialized),
        records_rejected_missing_time=sum(
            batch.records_rejected_missing_time for batch in materialized
        ),
        records_rejected_filter=sum(batch.records_rejected_filter for batch in materialized),
        unique_sources=unique_sources,
        score=score,
        missing_dimensions=missing,
        truncated=truncated,
    )


def build_envelope(
    *,
    tool_id: str,
    operation_id: str,
    request_id: str,
    requested_mode: str,
    executed_mode: str,
    outcome_status: OutcomeStatus,
    records: tuple[dict[str, object], ...],
    evidence_refs: tuple[MarketEvidenceRef, ...],
    coverage: CoverageReport,
    pit_proof: PitQueryProof,
    handler_id: str,
    seed: int,
    internal_work_units: int,
    warnings: Iterable[str] = (),
    downgrade_reason: str | None = None,
) -> MarketDerivativesToolResultEnvelope:
    execution = ExecutionReport(
        handler_id=handler_id,
        requested_mode=requested_mode,
        executed_mode=executed_mode,
        internal_work_units=internal_work_units,
        seed=seed,
        warnings=tuple(sorted(set(warnings))),
    )
    base = {
        "tool_id": tool_id,
        "operation_id": operation_id,
        "request_id": request_id,
        "outcome_status": outcome_status,
        "requested_mode": requested_mode,
        "executed_mode": executed_mode,
        "downgrade_reason": downgrade_reason,
        "records": records,
        "evidence_refs": evidence_refs,
        "coverage": coverage,
        "pit_proof": pit_proof,
        "execution": execution,
    }
    return MarketDerivativesToolResultEnvelope(result_hash=content_hash(base), **base)
