"""Evidence conversion for company records."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pydantic import JsonValue

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash
from .models import EvidenceReference
from .ports import parse_datetime


def evidence_from_record(record: Mapping[str, JsonValue], *, index: int) -> EvidenceReference:
    record_id = str(record.get("record_id") or f"record-{index}")
    artifact_id = str(record.get("artifact_id") or record.get("p2_artifact_id") or "unknown-artifact")
    source_id = str(record.get("source_id") or "unknown-source")
    quality_raw = record.get("source_quality", 1.0)
    quality = float(quality_raw) if isinstance(quality_raw, (int, float)) else 1.0
    return EvidenceReference(
        evidence_id=f"company:{artifact_id}:{record_id}", source_id=source_id,
        p2_artifact_id=artifact_id, p2_record_id=record_id,
        available_at=parse_datetime(record.get("available_at"), field_name="available_at"),
        content_hash=str(record.get("content_hash") or content_hash(dict(record))),
        source_quality=max(0.0, min(1.0, quality)),
    )


def evidence_for_records(records: Sequence[Mapping[str, JsonValue]]) -> tuple[EvidenceReference, ...]:
    unique = {ref.evidence_id: ref for ref in (evidence_from_record(r, index=i) for i, r in enumerate(records))}
    return tuple(unique[key] for key in sorted(unique))
