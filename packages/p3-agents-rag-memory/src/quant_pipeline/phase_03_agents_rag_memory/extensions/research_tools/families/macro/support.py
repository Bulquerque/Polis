from __future__ import annotations

from collections.abc import Iterable, Mapping

from pydantic import JsonValue

from ._compat import content_hash
from .normalization import available_at, observation_date, series_id
from .ports import VisibleMacroRecordBatch
from .request_contracts import MacroToolCallContext
from .result_contracts import (
    CoverageReport,
    ExecutionReport,
    MacroEvidenceRef,
    MacroToolResultEnvelope,
    PitQueryProof,
)
from .types import MacroMode, OutcomeStatus, VintagePolicy

_MODE_COST = {
    MacroMode.LOOKUP.value: 1.0,
    MacroMode.CONTEXT.value: 3.0,
    MacroMode.VINTAGE_ANALYSIS.value: 6.0,
}


def build_evidence(
    rows: Iterable[Mapping[str, object]],
    *,
    view_name: str,
) -> tuple[MacroEvidenceRef, ...]:
    refs: dict[str, MacroEvidenceRef] = {}
    for index, row in enumerate(rows):
        ref = _evidence_ref(row, view_name=view_name, index=index)
        refs[ref.evidence_id] = ref
    return tuple(sorted(refs.values(), key=lambda item: item.evidence_id))


def _evidence_ref(
    row: Mapping[str, object],
    *,
    view_name: str,
    index: int,
) -> MacroEvidenceRef:
    sid = series_id(row) or str(row.get("factor_id") or row.get("asset_id") or "unknown")
    try:
        observed = observation_date(row).isoformat()
    except ValueError:
        observed = str(row.get("valid_from") or available_at(row).date().isoformat())
    source_id = str(row.get("source_id") or "unknown")
    lineage = str(row.get("lineage_id") or row.get("p2_lineage_id") or "") or None
    artifact_id = str(row.get("artifact_id") or view_name)
    record_id = str(row.get("record_id") or f"{sid}:{observed}:{index}")
    visible_at = available_at(row)
    digest = content_hash(row)
    quality = float(row.get("source_quality") or row.get("source_quality_score") or 1.0)
    return MacroEvidenceRef(
        evidence_id=f"macro:{digest[:24]}",
        source_id=source_id,
        p2_artifact_id=artifact_id,
        p2_record_id=record_id,
        p2_lineage_id=lineage,
        available_at=visible_at,
        content_hash=digest,
        source_quality=max(0.0, min(1.0, quality)),
    )


def build_pit_proof(
    batches: Iterable[VisibleMacroRecordBatch],
    *,
    context: MacroToolCallContext,
    vintage_policy: VintagePolicy,
    evidence_refs: tuple[MacroEvidenceRef, ...],
) -> PitQueryProof:
    materialized = tuple(batches)
    base = {
        "policy_version": "p3.s37.pit.v1",
        "decision_time": context.decision_time,
        "vintage_policy": vintage_policy.value,
        "records_scanned": sum(item.records_scanned for item in materialized),
        "records_visible": sum(len(item.rows) for item in materialized),
        "records_rejected_future": sum(item.records_rejected_future for item in materialized),
        "records_rejected_missing_time": sum(
            item.records_rejected_missing_time for item in materialized
        ),
        "records_rejected_filter": sum(
            item.records_rejected_filter for item in materialized
        ),
        "earliest_available_at": min(
            (item.available_at for item in evidence_refs),
            default=None,
        ),
        "latest_available_at": max(
            (item.available_at for item in evidence_refs),
            default=None,
        ),
        "snapshot_id": context.snapshot_id,
        "input_hashes": tuple(
            sorted({digest for batch in materialized for digest in batch.input_hashes})
        ),
    }
    return PitQueryProof(**base, proof_hash=content_hash(base))


def build_envelope(
    *,
    operation_id: str,
    context: MacroToolCallContext,
    requested_mode: str,
    executed_mode: str,
    records: tuple[dict[str, JsonValue], ...],
    batches: tuple[VisibleMacroRecordBatch, ...],
    source_rows: tuple[Mapping[str, object], ...],
    vintage_policy: VintagePolicy,
    series_requested: int,
    series_returned: int,
    missing_series: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
    outcome_status: OutcomeStatus | None = None,
    downgrade_reason: str | None = None,
    truncated: bool = False,
) -> MacroToolResultEnvelope:
    evidence = build_evidence(source_rows, view_name="macro") if source_rows else ()
    pit = build_pit_proof(
        batches,
        context=context,
        vintage_policy=vintage_policy,
        evidence_refs=evidence,
    )
    base = _envelope_base(
        operation_id=operation_id,
        context=context,
        requested_mode=requested_mode,
        executed_mode=executed_mode,
        records=records,
        batches=batches,
        evidence=evidence,
        pit=pit,
        series_requested=series_requested,
        series_returned=series_returned,
        missing_series=missing_series,
        warnings=warnings,
        outcome_status=outcome_status,
        downgrade_reason=downgrade_reason,
        truncated=truncated,
    )
    hash_payload = _serialized_envelope(base)
    return MacroToolResultEnvelope(**base, result_hash=content_hash(hash_payload))


def _envelope_base(
    *,
    operation_id: str,
    context: MacroToolCallContext,
    requested_mode: str,
    executed_mode: str,
    records: tuple[dict[str, JsonValue], ...],
    batches: tuple[VisibleMacroRecordBatch, ...],
    evidence: tuple[MacroEvidenceRef, ...],
    pit: PitQueryProof,
    series_requested: int,
    series_returned: int,
    missing_series: tuple[str, ...],
    warnings: tuple[str, ...],
    outcome_status: OutcomeStatus | None,
    downgrade_reason: str | None,
    truncated: bool,
) -> dict[str, object]:
    status = outcome_status or (
        OutcomeStatus.PASS if records else OutcomeStatus.EMPTY_VALID
    )
    return {
        "operation_id": operation_id,
        "request_id": context.request_id,
        "outcome_status": status,
        "requested_mode": requested_mode,
        "executed_mode": executed_mode,
        "downgrade_reason": downgrade_reason,
        "records": records,
        "evidence_refs": evidence,
        "coverage": _coverage(
            records, batches, series_requested, series_returned,
            missing_series, warnings, truncated,
        ),
        "provenance": _provenance(context, evidence, pit),
        "pit_proof": pit,
        "execution": _execution(records, pit, executed_mode, warnings, batches),
    }


def _coverage(
    records: tuple[dict[str, JsonValue], ...],
    batches: tuple[VisibleMacroRecordBatch, ...],
    series_requested: int,
    series_returned: int,
    missing_series: tuple[str, ...],
    warnings: tuple[str, ...],
    truncated: bool,
) -> CoverageReport:
    requested_count = max(sum(len(batch.rows) for batch in batches), len(records))
    score = 1.0 if series_requested == 0 else series_returned / series_requested
    return CoverageReport(
        score=max(0.0, min(1.0, score)),
        records_requested=requested_count,
        records_returned=len(records),
        series_requested=series_requested,
        series_returned=series_returned,
        missing_series=missing_series,
        missing_dimensions=tuple(sorted(set(warnings))),
        truncated=truncated,
    )


def _execution(
    records: tuple[dict[str, JsonValue], ...],
    pit: PitQueryProof,
    executed_mode: str,
    warnings: tuple[str, ...],
    batches: tuple[VisibleMacroRecordBatch, ...],
) -> ExecutionReport:
    return ExecutionReport(
        cost_units=_MODE_COST.get(executed_mode, 1.0),
        internal_subquery_count=len(batches),
        records_scanned=pit.records_scanned,
        records_returned=len(records),
        warnings=tuple(sorted(set(warnings))),
    )


def _provenance(
    context: MacroToolCallContext,
    evidence: tuple[MacroEvidenceRef, ...],
    pit: PitQueryProof,
) -> dict[str, JsonValue]:
    return {
        "snapshot_id": context.snapshot_id,
        "evidence_ids": [item.evidence_id for item in evidence],
        "input_hashes": list(pit.input_hashes),
        "source_ids": sorted({item.source_id for item in evidence}),
    }


def _serialized_envelope(base: Mapping[str, object]) -> dict[str, object]:
    return {
        "envelope_version": "1.0.0",
        "tool_id": "macro.observation.v1",
        **{
            key: value.model_dump(mode="json") if hasattr(value, "model_dump") else value
            for key, value in base.items()
        },
    }
