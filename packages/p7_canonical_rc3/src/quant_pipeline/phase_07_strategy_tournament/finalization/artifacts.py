"""Canonical serialization, artifact construction and integrity validation."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Iterable, Mapping

from pydantic import BaseModel

from .boundary.base import ArtifactEnvelope, ArtifactReference
from .errors import ErrorContext, IntegrityViolation


def _json_safe(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return _json_safe(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_json_safe(item) for item in value)
    if isinstance(value, float) and not (value == value and abs(value) != float("inf")):
        return {"__non_finite__": repr(value)}
    return value


def canonical_json_bytes(value: object) -> bytes:
    safe = _json_safe(value)
    return json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_value(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _content_payload(envelope: ArtifactEnvelope) -> dict[str, object]:
    return {
        "artifact_name": envelope.artifact_name,
        "schema_version": envelope.schema_version,
        "producer_phase": envelope.producer_phase,
        "producer_module_id": envelope.producer_module_id,
        "run_id": envelope.run_id,
        "cycle_id": envelope.cycle_id,
        "decision_time": envelope.decision_time,
        "available_at": envelope.available_at,
        "created_at": envelope.created_at,
        "record_count": envelope.record_count,
        "lineage_id": envelope.lineage_id,
        "records": envelope.records,
    }


def build_artifact(
    *,
    artifact_name: str,
    schema_version: str,
    producer_module_id: str,
    run_id: str,
    cycle_id: str,
    decision_time: datetime,
    available_at: datetime,
    created_at: datetime,
    lineage_id: str,
    records: Iterable[BaseModel | Mapping[str, object]],
) -> ArtifactEnvelope:
    wire_records = [record.model_dump(mode="json") if isinstance(record, BaseModel) else dict(record) for record in records]
    wire_records.sort(key=lambda item: canonical_json_bytes(item))
    provisional = ArtifactEnvelope(
        artifact_id="pending",
        artifact_name=artifact_name,
        schema_version=schema_version,
        producer_phase="P7",
        producer_module_id=producer_module_id,
        run_id=run_id,
        cycle_id=cycle_id,
        decision_time=decision_time,
        available_at=available_at,
        created_at=created_at,
        content_sha256="0" * 64,
        record_count=len(wire_records),
        lineage_id=lineage_id,
        records=tuple(wire_records),
    )
    digest = sha256_value(_content_payload(provisional))
    return provisional.model_copy(update={"artifact_id": f"{artifact_name}:{digest[:20]}", "content_sha256": digest})


def validate_artifact_integrity(envelope: ArtifactEnvelope, module_id: str) -> None:
    actual = sha256_value(_content_payload(envelope))
    if actual != envelope.content_sha256:
        raise IntegrityViolation(
            "P7_ARTIFACT_HASH_MISMATCH",
            f"hash mismatch for {envelope.artifact_name}",
            ErrorContext(module_id=module_id, artifact_ids=(envelope.artifact_id,)),
        )


def artifact_reference(envelope: ArtifactEnvelope) -> ArtifactReference:
    return ArtifactReference(
        artifact_name=envelope.artifact_name,
        artifact_id=envelope.artifact_id,
        content_sha256=envelope.content_sha256,
        schema_version=envelope.schema_version,
        record_count=envelope.record_count,
    )
