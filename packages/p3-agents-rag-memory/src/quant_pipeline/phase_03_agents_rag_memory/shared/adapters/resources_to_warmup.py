from __future__ import annotations

from typing import Any, Mapping

from quant_pipeline.phase_03_agents_rag_memory.shared.contracts import model_or_mapping
from quant_pipeline.phase_03_agents_rag_memory.foundation.warmup_memory.replay.models import (
    ArtifactRef,
    FoundationResourceManifest,
)


def _ref(value: Mapping[str, Any], artifact_type: str | None = None) -> ArtifactRef:
    data = model_or_mapping(value)
    return ArtifactRef(
        artifact_id=data["artifact_id"],
        artifact_type=artifact_type or data.get("artifact_name", data["schema_id"].split(".")[0]),
        content_hash=data.get("content_hash", data.get("manifest_hash")),
        schema_id=data["schema_id"],
        schema_version=data["schema_version"],
    )


def to_warmup_resource_manifest(
    *,
    run_id: str,
    snapshot_id: str,
    rag_index_artifact: Mapping[str, Any],
    graph_rag_artifact: Mapping[str, Any],
    memory_access_policy: Mapping[str, Any],
    tool_registry: Mapping[str, Any],
    entitlement_panel: Mapping[str, Any],
    gateway_policy: Mapping[str, Any],
    prompt_bundle: Mapping[str, Any],
    model_registry: Mapping[str, Any],
    status: str,
    degraded_capabilities: tuple[str, ...] = (),
) -> FoundationResourceManifest:
    """Build the exact resource manifest consumed by warm-up from real resource artifacts."""

    refs = [
        _ref(rag_index_artifact), _ref(graph_rag_artifact), _ref(memory_access_policy),
        _ref(tool_registry), _ref(entitlement_panel), _ref(gateway_policy),
        _ref(prompt_bundle), _ref(model_registry),
    ]
    from quant_pipeline.phase_03_agents_rag_memory.shared.contracts import content_hash
    payload = {
        "schema_id": "p3_foundation_resource_manifest.v1",
        "schema_version": "1.0.0",
        "artifact_id": f"foundation-resources-{snapshot_id}",
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "rag_index_ref": refs[0],
        "graph_rag_ref": refs[1],
        "memory_policy_ref": refs[2],
        "tool_registry_ref": refs[3],
        "entitlement_ref": refs[4],
        "gateway_policy_ref": refs[5],
        "prompt_bundle_ref": refs[6],
        "model_registry_ref": refs[7],
        "status": status,
        "degraded_capabilities": degraded_capabilities,
    }
    payload["manifest_hash"] = content_hash(payload)
    return FoundationResourceManifest.model_validate(payload, strict=True)
