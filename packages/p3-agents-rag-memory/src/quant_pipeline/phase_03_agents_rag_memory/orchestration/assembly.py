"""Assembly of the canonical P3 foundation resource and runtime manifests."""

from __future__ import annotations

from ..integration.pointers import artifact_pointer
from ..integration.projections import identity_from_snapshot
from ..shared.contracts import (
    ArtifactPointer,
    FoundationResourceManifest,
    FoundationRuntimeManifest,
    FoundationGovernanceView,
    GovernanceSection,
    KnowledgeRuntimeView,
    KnowledgeSection,
    MemoryRuntimeView,
    MemorySection,
    PopulationRuntimeView,
    PopulationSection,
    ReadinessStatus,
    RunIdentity,
    SocialGraphRuntimeView,
    StateRuntimeView,
    StateSection,
    ToolRuntimeView,
    ToolingSection,
    build_resource_manifest_hash,
    build_runtime_manifest_hash,
)


def _view_pointer(view: object, *, producer_module_id: str) -> ArtifactPointer:
    payload = view.model_dump(mode="python")  # type: ignore[attr-defined]
    return artifact_pointer(
        payload["artifact_name"],
        payload,
        producer_module_id=producer_module_id,
        storage_location=f"memory://integration-view/{payload['artifact_id']}",
    )


def _readiness(
    degraded_capabilities: tuple[str, ...],
    blocking_reasons: tuple[str, ...],
) -> ReadinessStatus:
    if blocking_reasons:
        return ReadinessStatus.BLOCKED
    if degraded_capabilities:
        return ReadinessStatus.DEGRADED
    return ReadinessStatus.READY


def build_foundation_resource_manifest(
    *,
    identity: RunIdentity,
    knowledge_view: KnowledgeRuntimeView,
    memory_view: MemoryRuntimeView,
    tool_view: ToolRuntimeView,
    prompt_bundle: ArtifactPointer,
    model_registry: ArtifactPointer,
    degraded_capabilities: tuple[str, ...] = (),
    blocking_reasons: tuple[str, ...] = (),
    knowledge_view_ref: ArtifactPointer | None = None,
    memory_view_ref: ArtifactPointer | None = None,
    tool_view_ref: ArtifactPointer | None = None,
) -> FoundationResourceManifest:
    """Build the reference-only resource boundary consumed by warm-up and live runtime."""

    payload = {
        "artifact_id": f"foundation-resources-{identity.snapshot_id}",
        "identity": identity,
        "knowledge": KnowledgeSection(
            knowledge_view=knowledge_view_ref or _view_pointer(knowledge_view, producer_module_id="P3.S13.M02")
        ),
        "memory": MemorySection(
            memory_view=memory_view_ref or _view_pointer(memory_view, producer_module_id="P3.S14.M02")
        ),
        "tooling": ToolingSection(
            tool_view=tool_view_ref or _view_pointer(tool_view, producer_module_id="P3.S16.M02")
        ),
        "prompt_bundle": prompt_bundle,
        "model_registry": model_registry,
        "status": _readiness(degraded_capabilities, blocking_reasons),
        "degraded_capabilities": degraded_capabilities,
        "blocking_reasons": blocking_reasons,
        "content_hash": "0" * 64,
    }
    payload["content_hash"] = build_resource_manifest_hash(payload)
    return FoundationResourceManifest.model_validate(payload, strict=True)


def build_foundation_runtime_manifest(
    *,
    identity: RunIdentity,
    governance_view: FoundationGovernanceView,
    population_view: PopulationRuntimeView,
    social_graph_view: SocialGraphRuntimeView,
    state_view: StateRuntimeView,
    knowledge_view: KnowledgeRuntimeView,
    memory_view: MemoryRuntimeView,
    tool_view: ToolRuntimeView,
    capabilities: tuple[str, ...],
    degraded_capabilities: tuple[str, ...] = (),
    blocking_reasons: tuple[str, ...] = (),
    governance_view_ref: ArtifactPointer | None = None,
    population_view_ref: ArtifactPointer | None = None,
    social_graph_view_ref: ArtifactPointer | None = None,
    state_view_ref: ArtifactPointer | None = None,
    knowledge_view_ref: ArtifactPointer | None = None,
    memory_view_ref: ArtifactPointer | None = None,
    tool_view_ref: ArtifactPointer | None = None,
) -> FoundationRuntimeManifest:
    """Build the single stable handoff from foundation to runtime."""

    payload = {
        "artifact_id": f"foundation-runtime-{identity.snapshot_id}",
        "identity": identity,
        "governance": GovernanceSection(
            governance_view=governance_view_ref or _view_pointer(governance_view, producer_module_id="P3.S4.M02")
        ),
        "population": PopulationSection(
            population_view=population_view_ref or _view_pointer(population_view, producer_module_id="P3.S7.M02"),
            social_graph_view=social_graph_view_ref or _view_pointer(social_graph_view, producer_module_id="P3.S8.M02"),
        ),
        "state": StateSection(state_view=state_view_ref or _view_pointer(state_view, producer_module_id="P3.S11.M03")),
        "knowledge": KnowledgeSection(
            knowledge_view=knowledge_view_ref or _view_pointer(knowledge_view, producer_module_id="P3.S13.M02")
        ),
        "memory": MemorySection(memory_view=memory_view_ref or _view_pointer(memory_view, producer_module_id="P3.S14.M02")),
        "tooling": ToolingSection(tool_view=tool_view_ref or _view_pointer(tool_view, producer_module_id="P3.S16.M02")),
        "status": _readiness(degraded_capabilities, blocking_reasons),
        "capabilities": capabilities,
        "degraded_capabilities": degraded_capabilities,
        "blocking_reasons": blocking_reasons,
        "content_hash": "0" * 64,
    }
    payload["content_hash"] = build_runtime_manifest_hash(payload)
    return FoundationRuntimeManifest.model_validate(payload, strict=True)


__all__ = [
    "artifact_pointer",
    "build_foundation_resource_manifest",
    "build_foundation_runtime_manifest",
    "identity_from_snapshot",
]
