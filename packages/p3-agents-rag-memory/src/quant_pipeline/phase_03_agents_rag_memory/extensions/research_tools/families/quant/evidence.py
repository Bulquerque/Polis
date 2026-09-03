"""Evidence conversion for normalized quantitative records."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import JsonValue

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash

from .models import EvidenceReference
from .ports import QuantDataError, parse_datetime


def evidence_from_record(record: Mapping[str, JsonValue], *, index: int) -> EvidenceReference:
    record_id = str(
        record.get("record_id")
        or record.get("p2_record_id")
        or record.get("lineage_id")
        or record.get("observation_key")
        or f"record-{index}"
    )
    source_id = str(record.get("source_id") or "unknown-source")
    artifact_value = (
        record.get("artifact_id")
        or record.get("p2_artifact_id")
        or record.get("source_artifact_id")
    )
    if artifact_value is None:
        raise QuantDataError("evidence record is missing artifact_id/p2_artifact_id/source_artifact_id")
    artifact_id = str(artifact_value)
    available_at = parse_datetime(record.get("available_at"), field_name="available_at")
    quality_raw = record.get("source_quality", 1.0)
    quality = float(quality_raw) if isinstance(quality_raw, (int, float)) else 1.0
    quality = min(max(quality, 0.0), 1.0)
    supplied_hash = record.get("content_hash")
    if supplied_hash is not None:
        record_hash = str(supplied_hash)
    else:
        hash_payload = dict(record)
        hash_payload.pop("content_hash", None)
        record_hash = content_hash(hash_payload)
    return EvidenceReference(
        evidence_id=f"quant:{artifact_id}:{record_id}",
        source_id=source_id,
        p2_artifact_id=artifact_id,
        p2_record_id=record_id,
        available_at=available_at,
        content_hash=record_hash,
        source_quality=quality,
    )


def evidence_for_records(records: Sequence[Mapping[str, JsonValue]]) -> tuple[EvidenceReference, ...]:
    refs = [evidence_from_record(record, index=index) for index, record in enumerate(records)]
    unique = {ref.evidence_id: ref for ref in refs}
    return tuple(unique[key] for key in sorted(unique))
