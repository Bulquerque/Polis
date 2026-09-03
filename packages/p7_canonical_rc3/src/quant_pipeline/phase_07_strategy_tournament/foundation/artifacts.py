"""Artifact construction and validation helpers."""

from __future__ import annotations

from collections.abc import Iterable
from pydantic import JsonValue

from .canonical import content_sha256
from .models import ArtifactEnvelope, ModuleContext


def create_artifact(
    *,
    artifact_name: str,
    records: Iterable[dict[str, JsonValue]],
    producer_module_id: str,
    context: ModuleContext,
    grain: str,
    schema_version: str = "2.0.0",
    capability_status: str = "AVAILABLE",
) -> ArtifactEnvelope:
    ordered_records = tuple(records)
    base = {
        "artifact_id": f"{artifact_name}:{context.run_id}:{context.cycle_id}",
        "artifact_name": artifact_name,
        "schema_version": schema_version,
        "producer_phase": "P7",
        "producer_module_id": producer_module_id,
        "destination_phase": "P7",
        "pipeline_version": context.pipeline_version,
        "run_id": context.run_id,
        "cycle_id": context.cycle_id,
        "decision_time": context.decision_time,
        "available_at": context.available_at or context.decision_time,
        "created_at": context.created_at,
        "record_count": len(ordered_records),
        "grain": grain,
        "lineage_id": context.lineage_id,
        "capability_status": capability_status,
        "records": ordered_records,
    }
    placeholder = ArtifactEnvelope.model_validate({**base, "content_sha256": "0" * 64})
    wire_payload = placeholder.hash_payload()
    digest = content_sha256(wire_payload)
    return ArtifactEnvelope.model_validate({**wire_payload, "content_sha256": digest})


def verify_artifact_hash(envelope: ArtifactEnvelope) -> bool:
    return content_sha256(envelope.hash_payload()) == envelope.content_sha256
