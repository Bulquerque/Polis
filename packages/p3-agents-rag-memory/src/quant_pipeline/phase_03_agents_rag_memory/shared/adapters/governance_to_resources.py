from __future__ import annotations

from typing import Any, Mapping
from datetime import datetime

from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.document_rag.models import (
    PitValidatedContext,
    ProviderDescriptor,
    ProviderRegistry,
    ProviderStatus,
    RunSnapshot,
)
from quant_pipeline.phase_03_agents_rag_memory.shared.contracts import content_hash, model_or_mapping


def to_knowledge_snapshot(snapshot: Mapping[str, Any]) -> RunSnapshot:
    """Project the canonical governance snapshot into the reproducible S12/S13 build view."""

    source = model_or_mapping(snapshot)
    identity = source["identity"]
    temporal = source["temporal"]
    config_hashes = {str(item["config_id"]): str(item["content_hash"]) for item in source.get("configs", [])}
    provider_fingerprints = {
        str(item["provider_id"]): content_hash(item) for item in source.get("providers", [])
    }
    payload = {
        "schema_id": "phase3_run_snapshot.s12.v1",
        "schema_version": "1.0.0",
        "run_id": identity["run_id"],
        "snapshot_id": identity["snapshot_id"],
        "as_of_time": datetime.fromisoformat(str(temporal["as_of"]).replace("Z", "+00:00")),
        "pipeline_version": identity["pipeline_version"],
        "architecture_revision": identity["architecture_revision"],
        "config_hashes": config_hashes,
        "provider_fingerprints": provider_fingerprints,
        "timezone": temporal.get("timezone", "UTC"),
    }
    return RunSnapshot.model_validate(payload, strict=True)


def to_knowledge_context(
    pit_context: Mapping[str, Any],
    artifacts_by_name: Mapping[str, Mapping[str, Any]],
) -> PitValidatedContext:
    """Materialize accepted P2 documents referenced by governance authority's PIT decision.

    The adapter never bypasses the governance accepted-record lists. Source content must be supplied by
    the caller through an explicit artifact mapping; missing artifacts or records fail closed.
    """

    source = model_or_mapping(pit_context)
    document_view = next(
        (item for item in source.get("artifact_views", []) if item["source_artifact_ref"]["artifact_name"] == "clean_document_panel"),
        None,
    )
    if document_view is None:
        raise ValueError("PIT context does not reference clean_document_panel")
    document_artifact = artifacts_by_name.get("clean_document_panel")
    if document_artifact is None:
        raise ValueError("clean_document_panel bytes were not supplied to knowledge adapter")
    accepted = set(document_view["accepted_record_ids"])
    records: list[dict[str, object]] = []
    for record in document_artifact.get("records", []):
        if record.get("document_id") not in accepted:
            continue
        records.append({
            "record_type": "document",
            "document_id": record["document_id"],
            "source_id": record["source_id"],
            "content": record["document_text_or_path"],
            "event_time": None,
            "effective_time": None,
            "available_at": record["available_at"],
            "ingested_at": record.get("ingested_at"),
            "source_quality": float(record.get("source_quality_score", 1.0)),
            "entities": tuple(record.get("entities", ())),
            "underlyings": tuple(record.get("underlyings", ())),
            "metadata": {
                "document_type": record.get("document_type", "unknown"),
                "document_title": record.get("document_title", ""),
                "language": record.get("language", "unknown"),
                "reference_date": record.get("reference_date"),
            },
            "lineage_refs": (record.get("lineage_id", document_artifact.get("lineage_id", "unknown")),),
        })
    missing = accepted - {str(item["document_id"]) for item in records}
    if missing:
        raise ValueError(f"Accepted PIT documents are missing from supplied artifact: {sorted(missing)}")
    return PitValidatedContext.model_validate({
        "schema_id": "pit_validated_context.s12.v1",
        "schema_version": "1.0.0",
        "records": tuple(records),
        "lineage_id": source["lineage_id"],
    }, strict=True)


def build_offline_provider_registry() -> ProviderRegistry:
    """Deterministic no-network provider registry for local qualification and replay."""

    descriptor = ProviderDescriptor(
        provider_id="offline_hashing",
        interface_id="EmbeddingProvider",
        adapter_id="sha256_hash_embedding",
        adapter_version="1.0.0",
        status=ProviderStatus.CONNECTED,
        model_id="offline-hash-64",
        model_revision="1.0.0",
        dimensions=64,
        supports_batching=True,
        supports_available_at_filter=True,
        supports_snapshot_pin=True,
        qualification_status="QUALIFIED_LOCAL_DETERMINISTIC",
        fingerprint=content_hash({"provider_id":"offline_hashing","model":"offline-hash-64","revision":"1.0.0"}),
    )
    return ProviderRegistry(providers=(descriptor,))
