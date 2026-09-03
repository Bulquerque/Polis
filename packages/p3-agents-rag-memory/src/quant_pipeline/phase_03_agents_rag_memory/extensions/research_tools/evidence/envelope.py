"""Build canonical S40 envelopes from S21 raw tool results."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash, utc
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import RawToolResultRecord, ToolCallAuditRecord, ToolExecutionStatus

from ..runtime.models import (
    CoverageReport, ExecutionReport, OutcomeStatus, PitProof, ProvenanceEvidence,
    ProvenanceReport, ResearchToolResultEnvelope,
)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _number(value: object, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return utc(value)
    if isinstance(value, str):
        try:
            return utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _outcome(value: object) -> OutcomeStatus:
    try:
        return OutcomeStatus(str(value))
    except ValueError:
        return OutcomeStatus.DEGRADED


def parse_provenance_evidence(payload: Mapping[str, object]) -> tuple[ProvenanceEvidence, ...]:
    raw_items = payload.get("evidence_refs", ())
    records: dict[str, ProvenanceEvidence] = {}
    for raw in raw_items if isinstance(raw_items, list) else ():
        item = _evidence(raw)
        if item is None:
            continue
        prior = records.get(item.evidence_id)
        if prior is not None and prior != item:
            raise ValueError(f"conflicting evidence definition: {item.evidence_id}")
        records[item.evidence_id] = item
    return tuple(records[key] for key in sorted(records))


def _evidence(raw: object) -> ProvenanceEvidence | None:
    if not isinstance(raw, Mapping):
        return None
    evidence_id, source_id = raw.get("evidence_id"), raw.get("source_id")
    available_at, digest = _time(raw.get("available_at")), raw.get("content_hash")
    valid = isinstance(evidence_id, str) and evidence_id and isinstance(source_id, str) and source_id
    if not valid or available_at is None or not isinstance(digest, str) or len(digest) != 64:
        return None
    return ProvenanceEvidence(
        evidence_id=evidence_id,
        source_id=source_id,
        available_at=available_at,
        content_hash=digest,
        source_quality=max(0.0, min(1.0, _number(raw.get("source_quality"), 1.0))),
        p1_raw_artifact_id=_optional_text(raw, "p1_raw_artifact_id"),
        p2_artifact_id=_optional_text(raw, "p2_artifact_id"),
        p2_record_id=_optional_text(raw, "p2_record_id"),
        p2_lineage_id=_optional_text(raw, "p2_lineage_id"),
    )


def _optional_text(raw: Mapping[str, object], key: str) -> str | None:
    value = raw.get(key)
    return str(value) if value else None


def coverage_from_payload(payload: Mapping[str, object]) -> CoverageReport:
    raw = _mapping(payload.get("coverage"))
    missing = raw.get("missing_requirements", ())
    return CoverageReport(
        score=max(0.0, min(1.0, _number(raw.get("score")))),
        observations_requested=_count(raw.get("observations_requested")),
        observations_used=_count(raw.get("observations_used")),
        observations_rejected_future=_count(raw.get("observations_rejected_future")),
        observations_rejected_quality=_count(raw.get("observations_rejected_quality")),
        missing_requirements=tuple(sorted(item for item in missing if isinstance(item, str) and item)),
    )


def build_result_envelope(
    *, result: RawToolResultRecord, audit: ToolCallAuditRecord, decision_time: datetime
) -> ResearchToolResultEnvelope | None:
    if result.status is not ToolExecutionStatus.SUCCEEDED or result.canonical_payload is None:
        return None
    payload = result.canonical_payload
    evidence = parse_provenance_evidence(payload)
    coverage = coverage_from_payload(payload)
    provenance = _provenance(evidence)
    pit_proof = _pit_proof(result, evidence, coverage, decision_time)
    execution = _execution(result, audit)
    body = _envelope_body(result, payload, coverage, provenance, pit_proof, execution)
    return ResearchToolResultEnvelope(**body, envelope_hash=content_hash(body))


def _provenance(evidence: tuple[ProvenanceEvidence, ...]) -> ProvenanceReport:
    body = {
        "evidence": evidence,
        "source_families": tuple(sorted({item.source_id.split(":", 1)[0] for item in evidence})),
        "source_count": len({item.source_id for item in evidence}),
        "lineage_complete": all(item.p2_artifact_id is not None for item in evidence) if evidence else True,
    }
    return ProvenanceReport(**body, provenance_hash=content_hash(body))


def _pit_proof(
    result: RawToolResultRecord,
    evidence: tuple[ProvenanceEvidence, ...],
    coverage: CoverageReport,
    decision_time: datetime,
) -> PitProof:
    latest = result.available_at or (max((item.available_at for item in evidence), default=None)) or utc(decision_time)
    body = {
        "decision_time": utc(decision_time),
        "latest_available_at": latest,
        "records_rejected_future": coverage.observations_rejected_future,
        "input_hashes": tuple(sorted({item.content_hash for item in evidence})),
    }
    return PitProof(**body, proof_hash=content_hash(body))


def _execution(result: RawToolResultRecord, audit: ToolCallAuditRecord) -> ExecutionReport:
    trace_id = content_hash({
        "execution_id": result.execution_id,
        "request_id": result.tool_call_request_id,
        "response_hash": result.response_hash,
    })[:32]
    return ExecutionReport(
        execution_id=result.execution_id,
        provider_id=result.provider_id,
        latency_ms=result.latency_ms,
        cost_units=result.cost_units,
        deterministic_or_seeded=True,
        request_hash=audit.request_hash,
        response_hash=result.response_hash,
        trace_id=trace_id,
    )


def _envelope_body(
    result: RawToolResultRecord,
    payload: Mapping[str, object],
    coverage: CoverageReport,
    provenance: ProvenanceReport,
    pit_proof: PitProof,
    execution: ExecutionReport,
) -> dict[str, object]:
    requested = str(payload.get("requested_mode", "UNSPECIFIED"))
    return {
        "execution_id": result.execution_id,
        "request_id": result.tool_call_request_id,
        "cognition_transaction_id": result.cognition_transaction_id,
        "person_id": result.person_id,
        "tool_id": result.tool_id,
        "operation_id": result.operation_id,
        "outcome_status": _outcome(payload.get("outcome_status", "DEGRADED")),
        "requested_mode": requested,
        "executed_mode": str(payload.get("executed_mode", requested)),
        "downgrade_reason": _optional_text(payload, "downgrade_reason"),
        "canonical_payload_hash": content_hash(payload),
        "evidence_refs": tuple(sorted(set(result.evidence_refs))),
        "coverage": coverage,
        "provenance": provenance,
        "pit_proof": pit_proof,
        "execution": execution,
        "reason_codes": tuple(item for item in payload.get("reason_codes", ()) if isinstance(item, str) and item),
    }
