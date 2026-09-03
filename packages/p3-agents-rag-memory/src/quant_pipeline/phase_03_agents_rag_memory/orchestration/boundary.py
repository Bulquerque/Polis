"""Canonical P3 boundary adapters.

The implementation of S1-S16 and S17-S31 has different internal models. This
module is the only place where those internal shapes are translated. All public
callers use Contract Pack V2 from :mod:`phase_03_agents_rag_memory.contracts`.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import datetime
from typing import Mapping
import re

from ..contracts import (
    ArtifactPointer as PublicPointer,
    ArtifactStatus,
    CrossPhaseOutputs,
    CycleKernelRequest as PublicCycleRequest,
    CycleKernelResult as PublicCycleResult,
    CycleStatus,
    ExecutionMode as PublicExecutionMode,
    FoundationRuntimeManifest as PublicFoundationManifest,
    LineageRecord as PublicLineage,
    LineageSource,
    P3CycleClosureManifest as PublicClosure,
    P4Outputs,
    P9Outputs,
    ReplayState as PublicReplayState,
    RunIdentity as PublicRunIdentity,
    StateSource as PublicStateSource,
    StorageReference,
    content_hash as public_content_hash,
)
from ..shared import contracts as foundation_contracts
from ..runtime_engine.contracts_internal import (
    ArtifactPointer as RuntimePointer,
    CycleKernelRequest as RuntimeCycleRequest,
    CycleKernelResult as RuntimeCycleResult,
    ExecutionMode as RuntimeExecutionMode,
    ExecutionStatus,
    FoundationGovernanceView as RuntimeGovernanceView,
    FoundationRuntimeManifest as RuntimeManifest,
    KnowledgeRuntimeView as RuntimeKnowledgeView,
    LineageRecord as RuntimeLineage,
    MemoryRuntimeView as RuntimeMemoryView,
    PopulationPersonRecord,
    PopulationRuntimeView as RuntimePopulationView,
    ReplayState as RuntimeReplayState,
    ResolvedArtifact,
    StateRuntimeView as RuntimeStateView,
    StructuralFieldPolicy,
    ToolRuntimeView as RuntimeToolView,
    content_hash as runtime_content_hash,
)
from ..runtime_engine.testing import InMemoryArtifactResolver
from .artifact_store import CanonicalArtifactStore


ARCHITECTURE_REVISION = "P3-FINAL"


@dataclass(frozen=True, slots=True)
class FoundationBundle:
    """Canonical manifest plus internal runtime materialization."""

    public_manifest: PublicFoundationManifest
    runtime_manifest: RuntimeManifest
    runtime_resolver: InMemoryArtifactResolver
    public_store: CanonicalArtifactStore


def _semver(value: str) -> str:
    return value if re.fullmatch(r"\d+\.\d+\.\d+", value) else "1.0.0"


def _public_status(value: object) -> ArtifactStatus:
    raw = str(getattr(value, "value", value))
    return ArtifactStatus("READY" if raw == "PASS" else raw)


def _runtime_status(value: object) -> ExecutionStatus:
    raw = str(getattr(value, "value", value))
    return ExecutionStatus("READY" if raw == "PASS" else raw)


def _producer(value: str | None) -> str:
    if value and re.fullmatch(r"P3\.S(?:[1-9]|[12][0-9]|3[0-1])\.M\d{2}", value):
        return value
    return "P3.ORCHESTRATOR"


def _public_pointer(pointer: foundation_contracts.ArtifactPointer) -> PublicPointer:
    storage = pointer.storage_ref
    return PublicPointer(
        artifact_name=pointer.artifact_name,
        schema_id=pointer.schema_id,
        schema_version=_semver(pointer.schema_version),
        artifact_id=pointer.artifact_id,
        content_hash=pointer.content_hash,
        status=_public_status(pointer.status),
        storage_ref=StorageReference(
            scheme=str(getattr(storage.scheme, "value", storage.scheme)),
            location=storage.location,
            version=storage.version,
        ),
        media_type=pointer.media_type,
        producer_module_id=_producer(pointer.producer_module_id),
        lineage_id=pointer.lineage_id,
        row_count=pointer.row_count,
        grain=tuple(pointer.grain),
        available_at=pointer.available_at,
    )


def _runtime_pointer(pointer: foundation_contracts.ArtifactPointer) -> RuntimePointer:
    storage = pointer.storage_ref
    return RuntimePointer(
        artifact_name=pointer.artifact_name,
        schema_id=pointer.schema_id,
        schema_version=_semver(pointer.schema_version),
        artifact_id=pointer.artifact_id,
        content_hash=pointer.content_hash,
        storage_ref=storage.location,
        producer_module_id=_producer(pointer.producer_module_id),
        status=_runtime_status(pointer.status),
        row_count=pointer.row_count,
        grain=tuple(pointer.grain),
        lineage_id=pointer.lineage_id,
    )


def _synthetic_foundation_pointer(name: str, schema_id: str) -> foundation_contracts.ArtifactPointer:
    payload = {"artifact_name": name, "records": [], "status": "EMPTY_VALID"}
    digest = foundation_contracts.content_hash(payload)
    return foundation_contracts.ArtifactPointer(
        artifact_name=name,
        schema_id=schema_id,
        schema_version="1.0.0",
        artifact_id=f"{name}-{digest[:16]}",
        content_hash=digest,
        status=foundation_contracts.ReadinessStatus.EMPTY_VALID,
        storage_ref=foundation_contracts.StorageReference(
            scheme=foundation_contracts.StorageScheme.MEMORY,
            location=f"memory://{name}/{digest}",
        ),
        producer_module_id="P3.ORCHESTRATOR",
        row_count=0,
    )


def _resolved_runtime(model: object, *, artifact_name: str, producer: str) -> ResolvedArtifact:
    payload = model.model_dump(mode="json")  # type: ignore[attr-defined]
    digest = runtime_content_hash(payload)
    pointer = RuntimePointer(
        artifact_name=artifact_name,
        schema_id=str(payload["schema_id"]),
        schema_version=str(payload["schema_version"]),
        artifact_id=f"{artifact_name}-{digest[:16]}",
        content_hash=digest,
        storage_ref=f"memory://integration/{artifact_name}/{digest}",
        producer_module_id=producer,
        status=_runtime_status(payload.get("status", "READY")),
        row_count=len(payload.get("records", [])) if isinstance(payload.get("records"), list) else None,
        grain=(),
        lineage_id=f"lineage-{artifact_name}-{digest[:12]}",
    )
    return ResolvedArtifact(pointer=pointer, payload=payload)


def _public_manifest_hash(payload: dict[str, object]) -> str:
    clean = dict(payload)
    clean.pop("content_hash", None)
    return public_content_hash(clean)


def _social_graph_runtime_pointer(
    social_graph: foundation_contracts.SocialGraphRuntimeView,
) -> RuntimePointer:
    payload = social_graph.model_dump(mode="json")
    digest = runtime_content_hash(payload)
    return RuntimePointer(
        artifact_name="validated_initial_social_graph",
        schema_id="validated_initial_social_graph.v1",
        schema_version="1.0.0",
        artifact_id=f"validated_initial_social_graph-{digest[:16]}",
        content_hash=digest,
        storage_ref=f"memory://validated_initial_social_graph/{digest}",
        producer_module_id="P3.S8.M02",
        status=ExecutionStatus.READY,
        row_count=len(social_graph.records),
        grain=("source_person_id", "target_person_id", "relationship_type"),
        lineage_id=social_graph.lineage.lineage_id,
    )


def _build_runtime_views(
    *,
    identity: foundation_contracts.RunIdentity,
    governance: foundation_contracts.FoundationGovernanceView,
    population: foundation_contracts.PopulationRuntimeView,
    social_graph: foundation_contracts.SocialGraphRuntimeView,
    state: foundation_contracts.StateRuntimeView,
    knowledge: foundation_contracts.KnowledgeRuntimeView,
    memory: foundation_contracts.MemoryRuntimeView,
    tooling: foundation_contracts.ToolRuntimeView,
    population_coverage_ratio: float,
) -> tuple[ResolvedArtifact, ...]:
    common = {
        "run_id": identity.run_id,
        "snapshot_id": identity.snapshot_id,
        "as_of_time": identity.as_of_time,
    }
    runtime_governance = RuntimeGovernanceView(
        **common,
        pipeline_version=identity.pipeline_version,
        architecture_revision=ARCHITECTURE_REVISION,
        pit_context=_runtime_pointer(governance.pit_context_ref),
        run_snapshot=_runtime_pointer(governance.run_snapshot_ref),
        model_cutoff_report=_runtime_pointer(governance.model_cutoff_view_ref),
        retro_policy_patch=_runtime_pointer(governance.active_feedback_ref),
        belief_feedback_bundle=_runtime_pointer(governance.active_feedback_ref),
        person_schema_policy=_runtime_pointer(governance.person_policy_ref),
        personality_tag_registry=_runtime_pointer(governance.tag_registry_ref),
        status=ExecutionStatus.READY,
    )
    runtime_population = RuntimePopulationView(
        **common,
        population_hash=population.content_hash,
        coverage_ratio=population_coverage_ratio,
        formula_id="p3.population.coverage",
        formula_version="1.0.0",
        population_manifest=_runtime_pointer(population.source_manifest_ref),
        social_graph=_social_graph_runtime_pointer(social_graph),
        records=tuple(
            PopulationPersonRecord(
                person_id=item.person_id,
                economic_role=item.economic_role,
                representation_weight=item.representation_weight,
                seed=item.deterministic_seed,
                availability_constraints=item.availability_constraints,
                capability_refs=tuple(score.capability_id for score in item.capabilities),
            )
            for item in population.records
        ),
        status=_runtime_status(population.status),
    )
    runtime_state = RuntimeStateView(
        **common,
        current_person_state=_runtime_pointer(state.current_person_state_ref),
        current_belief_state=_runtime_pointer(state.current_belief_state_ref),
        current_memory_state=_runtime_pointer(state.current_memory_state_ref),
        current_social_graph=_runtime_pointer(state.current_social_graph_ref),
        person_field_policy=StructuralFieldPolicy(
            structural=("person_id", "economic_role", "role_family", "representation_weight"),
            slow_moving=("capabilities", "availability_constraints"),
            dynamic=("belief_state", "memory_state", "attention", "fatigue"),
        ),
        status=ExecutionStatus.READY,
    )
    runtime_knowledge = RuntimeKnowledgeView(
        **common,
        rag_index=_runtime_pointer(knowledge.rag_index_ref),
        retrieval_manifest=_runtime_pointer(knowledge.retrieval_manifest_ref),
        graph_rag=_runtime_pointer(knowledge.graph_rag_ref),
        graph_evidence=_runtime_pointer(knowledge.graph_evidence_ref),
        capabilities=knowledge.capabilities,
        status=_runtime_status(knowledge.status),
    )
    runtime_memory = RuntimeMemoryView(
        **common,
        access_policy=_runtime_pointer(memory.access_policy_ref),
        memory_index=_runtime_pointer(memory.memory_index_ref),
        status=_runtime_status(memory.status),
    )
    runtime_tools = RuntimeToolView(
        **common,
        tool_registry=_runtime_pointer(tooling.tool_registry_ref),
        entitlement_panel=_runtime_pointer(tooling.entitlement_ref),
        gateway_policy=_runtime_pointer(tooling.gateway_policy_ref),
        audit_contract=_runtime_pointer(tooling.audit_contract_ref),
        status=_runtime_status(tooling.status),
    )
    return (
        _resolved_runtime(runtime_governance, artifact_name="foundation_governance_view", producer="P3.S4.M02"),
        _resolved_runtime(runtime_population, artifact_name="population_runtime_view", producer="P3.S7.M02"),
        _resolved_runtime(runtime_state, artifact_name="state_runtime_view", producer="P3.S11.M03"),
        _resolved_runtime(runtime_knowledge, artifact_name="knowledge_runtime_view", producer="P3.S13.M02"),
        _resolved_runtime(runtime_memory, artifact_name="memory_runtime_view", producer="P3.S14.M02"),
        _resolved_runtime(runtime_tools, artifact_name="tool_runtime_view", producer="P3.S16.M02"),
    )


def _foundation_status(
    *, degraded_capabilities: tuple[str, ...], blocking_reasons: tuple[str, ...]
) -> tuple[ExecutionStatus, ArtifactStatus]:
    if blocking_reasons:
        return ExecutionStatus.BLOCKED, ArtifactStatus.BLOCKED
    if degraded_capabilities:
        return ExecutionStatus.DEGRADED, ArtifactStatus.DEGRADED
    return ExecutionStatus.READY, ArtifactStatus.READY


def _build_runtime_manifest(
    *,
    identity: foundation_contracts.RunIdentity,
    resolved: tuple[ResolvedArtifact, ...],
    prompt_bundle: foundation_contracts.ArtifactPointer,
    model_registry: foundation_contracts.ArtifactPointer,
    capabilities: tuple[str, ...],
    degraded_capabilities: tuple[str, ...],
    blocking_reasons: tuple[str, ...],
) -> RuntimeManifest:
    by_name = {item.pointer.artifact_name: item for item in resolved}
    lineage = RuntimeLineage(
        lineage_id=f"lineage-foundation-{identity.snapshot_id}",
        producer_module_id="P3.ORCHESTRATOR",
        source_artifact_ids=tuple(item.pointer.artifact_id for item in resolved),
        source_hashes=tuple(item.pointer.content_hash for item in resolved),
    )
    runtime_status, _ = _foundation_status(
        degraded_capabilities=degraded_capabilities, blocking_reasons=blocking_reasons
    )
    base = dict(
        run_id=identity.run_id, snapshot_id=identity.snapshot_id, as_of_time=identity.as_of_time,
        artifact_id=f"foundation-runtime-{identity.snapshot_id}",
        pipeline_version=identity.pipeline_version, architecture_revision=ARCHITECTURE_REVISION,
        lineage=lineage, governance_view=by_name["foundation_governance_view"].pointer,
        population_view=by_name["population_runtime_view"].pointer,
        state_view=by_name["state_runtime_view"].pointer,
        knowledge_view=by_name["knowledge_runtime_view"].pointer,
        memory_view=by_name["memory_runtime_view"].pointer,
        tool_view=by_name["tool_runtime_view"].pointer,
        prompt_bundle=_runtime_pointer(prompt_bundle), model_registry=_runtime_pointer(model_registry),
        capabilities=capabilities, status=runtime_status,
        degraded_capabilities=degraded_capabilities, blocking_reasons=blocking_reasons,
    )
    provisional = RuntimeManifest.model_construct(**base, content_hash="0" * 64)
    return RuntimeManifest(
        **base,
        content_hash=runtime_content_hash(provisional.model_dump(mode="json", exclude={"content_hash"})),
    )


def _build_public_foundation_manifest(
    *,
    identity: foundation_contracts.RunIdentity,
    governance: foundation_contracts.FoundationGovernanceView,
    population: foundation_contracts.PopulationRuntimeView,
    social_graph: foundation_contracts.SocialGraphRuntimeView,
    state: foundation_contracts.StateRuntimeView,
    knowledge: foundation_contracts.KnowledgeRuntimeView,
    memory: foundation_contracts.MemoryRuntimeView,
    tooling: foundation_contracts.ToolRuntimeView,
    prompt_bundle: foundation_contracts.ArtifactPointer,
    model_registry: foundation_contracts.ArtifactPointer,
    capabilities: tuple[str, ...],
    degraded_capabilities: tuple[str, ...],
    blocking_reasons: tuple[str, ...],
) -> PublicFoundationManifest:
    public_identity = PublicRunIdentity(
        run_id=identity.run_id, snapshot_id=identity.snapshot_id, as_of_time=identity.as_of_time,
        pipeline_version=identity.pipeline_version, architecture_revision=ARCHITECTURE_REVISION,
    )
    pointers = {
        "governance": _public_pointer(_foundation_view_pointer(governance, "P3.S4.M02")),
        "population": _public_pointer(_foundation_view_pointer(population, "P3.S7.M02")),
        "social_graph": _public_pointer(_foundation_view_pointer(social_graph, "P3.S8.M02")),
        "state": _public_pointer(_foundation_view_pointer(state, "P3.S11.M03")),
        "knowledge": _public_pointer(_foundation_view_pointer(knowledge, "P3.S13.M02")),
        "memory": _public_pointer(_foundation_view_pointer(memory, "P3.S14.M02")),
        "tooling": _public_pointer(_foundation_view_pointer(tooling, "P3.S16.M02")),
    }
    lineage = PublicLineage(
        lineage_id=f"lineage-foundation-{identity.snapshot_id}",
        producer_module_id="P3.ORCHESTRATOR",
        sources=tuple(LineageSource(artifact_id=p.artifact_id, content_hash=p.content_hash) for p in pointers.values()),
        transformation_ids=("foundation_runtime_manifest.v2",),
    )
    _, public_status = _foundation_status(
        degraded_capabilities=degraded_capabilities, blocking_reasons=blocking_reasons
    )
    base: dict[str, object] = {
        "artifact_id": f"foundation-runtime-{identity.snapshot_id}", "identity": public_identity,
        "governance_view_ref": pointers["governance"], "population_view_ref": pointers["population"],
        "social_graph_view_ref": pointers["social_graph"], "state_view_ref": pointers["state"],
        "knowledge_view_ref": pointers["knowledge"], "memory_view_ref": pointers["memory"],
        "tool_view_ref": pointers["tooling"], "prompt_bundle_ref": _public_pointer(prompt_bundle),
        "model_registry_ref": _public_pointer(model_registry), "capabilities": capabilities,
        "status": public_status, "degraded_capabilities": degraded_capabilities,
        "blocking_reasons": blocking_reasons, "lineage": lineage, "content_hash": "0" * 64,
    }
    base["content_hash"] = _public_manifest_hash(base)
    return PublicFoundationManifest.model_validate(base, strict=True)


def build_foundation_bundle(
    *,
    identity: foundation_contracts.RunIdentity,
    governance: foundation_contracts.FoundationGovernanceView,
    population: foundation_contracts.PopulationRuntimeView,
    social_graph: foundation_contracts.SocialGraphRuntimeView,
    state: foundation_contracts.StateRuntimeView,
    knowledge: foundation_contracts.KnowledgeRuntimeView,
    memory: foundation_contracts.MemoryRuntimeView,
    tooling: foundation_contracts.ToolRuntimeView,
    capabilities: tuple[str, ...],
    population_coverage_ratio: float,
    prompt_bundle: foundation_contracts.ArtifactPointer | None = None,
    model_registry: foundation_contracts.ArtifactPointer | None = None,
    degraded_capabilities: tuple[str, ...] = (),
    blocking_reasons: tuple[str, ...] = (),
) -> FoundationBundle:
    """Create the definitive public manifest and internal runtime materialization."""
    prompt = prompt_bundle or _synthetic_foundation_pointer("prompt_bundle", "p3.prompt_bundle.v1")
    models = model_registry or _synthetic_foundation_pointer("model_registry", "p3.model_registry.v1")
    resolved = _build_runtime_views(
        identity=identity, governance=governance, population=population, social_graph=social_graph,
        state=state, knowledge=knowledge, memory=memory, tooling=tooling,
        population_coverage_ratio=population_coverage_ratio,
    )
    runtime_manifest = _build_runtime_manifest(
        identity=identity, resolved=resolved, prompt_bundle=prompt, model_registry=models,
        capabilities=capabilities, degraded_capabilities=degraded_capabilities,
        blocking_reasons=blocking_reasons,
    )
    public_manifest = _build_public_foundation_manifest(
        identity=identity, governance=governance, population=population, social_graph=social_graph,
        state=state, knowledge=knowledge, memory=memory, tooling=tooling, prompt_bundle=prompt,
        model_registry=models, capabilities=capabilities, degraded_capabilities=degraded_capabilities,
        blocking_reasons=blocking_reasons,
    )
    store = CanonicalArtifactStore()
    manifest_pointer = PublicPointer(
        artifact_name=public_manifest.artifact_name, schema_id=public_manifest.schema_id,
        schema_version=public_manifest.schema_version, artifact_id=public_manifest.artifact_id,
        content_hash=public_manifest.content_hash, status=public_manifest.status,
        storage_ref=StorageReference(scheme="memory", location=f"foundation/{public_manifest.artifact_id}"),
        producer_module_id="P3.ORCHESTRATOR", lineage_id=public_manifest.lineage.lineage_id,
        available_at=public_manifest.identity.as_of_time,
    )
    store.put(manifest_pointer, public_manifest)
    return FoundationBundle(
        public_manifest=public_manifest, runtime_manifest=runtime_manifest,
        runtime_resolver=InMemoryArtifactResolver(artifacts={item.pointer.artifact_id: item for item in resolved}),
        public_store=store,
    )

def _foundation_view_pointer(model: object, producer: str) -> foundation_contracts.ArtifactPointer:
    payload = model.model_dump(mode="python")  # type: ignore[attr-defined]
    digest = str(payload["content_hash"])
    return foundation_contracts.ArtifactPointer(
        artifact_name=str(payload["artifact_name"]),
        schema_id=str(payload["schema_id"]),
        schema_version=str(payload["schema_version"]),
        artifact_id=str(payload["artifact_id"]),
        content_hash=digest,
        status=foundation_contracts.ReadinessStatus(str(payload.get("status", "READY"))),
        storage_ref=foundation_contracts.StorageReference(
            scheme=foundation_contracts.StorageScheme.MEMORY,
            location=f"memory://integration-view/{payload['artifact_id']}",
        ),
        producer_module_id=producer,
        lineage_id=getattr(getattr(model, "lineage", None), "lineage_id", None),
        row_count=len(payload.get("records", [])) if isinstance(payload.get("records"), (list, tuple)) else None,
    )


def runtime_manifest_pointer(bundle: FoundationBundle) -> RuntimePointer:
    manifest = bundle.runtime_manifest
    return RuntimePointer(
        artifact_name=manifest.artifact_name,
        schema_id=manifest.schema_id,
        schema_version=manifest.schema_version,
        artifact_id=manifest.artifact_id,
        content_hash=manifest.content_hash,
        storage_ref=f"memory://foundation-manifest/{manifest.artifact_id}",
        producer_module_id="P3.ORCHESTRATOR",
        status=manifest.status,
        lineage_id=manifest.lineage.lineage_id,
    )


def _runtime_pointer_from_public(pointer: PublicPointer) -> RuntimePointer:
    storage = pointer.storage_ref
    location = f"{storage.scheme}://{storage.location}"
    return RuntimePointer(
        artifact_name=pointer.artifact_name,
        schema_id=pointer.schema_id,
        schema_version=pointer.schema_version,
        artifact_id=pointer.artifact_id,
        content_hash=pointer.content_hash,
        storage_ref=location,
        producer_module_id=pointer.producer_module_id,
        status=ExecutionStatus(pointer.status.value),
        row_count=pointer.row_count,
        grain=pointer.grain,
        lineage_id=pointer.lineage_id,
    )


def _runtime_lineage_from_public(lineage: PublicLineage) -> RuntimeLineage:
    return RuntimeLineage(
        lineage_id=lineage.lineage_id,
        producer_module_id=lineage.producer_module_id,
        source_artifact_ids=tuple(item.artifact_id for item in lineage.sources),
        source_hashes=tuple(item.content_hash for item in lineage.sources),
    )


def _runtime_replay_state(state: PublicReplayState) -> RuntimeReplayState:
    payload = {
        "schema_id": "p3.integration.replay_state.v1",
        "schema_version": "1.0.0",
        "run_id": state.identity.run_id,
        "snapshot_id": state.identity.snapshot_id,
        "cycle_id": state.source_cycle_id,
        "as_of_time": state.identity.as_of_time,
        "person_state": _runtime_pointer_from_public(state.person_state_ref),
        "belief_state": _runtime_pointer_from_public(state.belief_state_ref),
        "memory_state": _runtime_pointer_from_public(state.memory_state_ref),
        "social_graph": _runtime_pointer_from_public(state.social_graph_ref),
        "pending_stimuli": _runtime_pointer_from_public(state.pending_stimuli_ref),
        "belief_commitments": _runtime_pointer_from_public(state.belief_commitments_ref),
        "resource_manifest_ref": _runtime_pointer_from_public(state.foundation_manifest_ref),
        "audit_refs": tuple(_runtime_pointer_from_public(item) for item in state.audit_refs),
        "status": ExecutionStatus.READY,
        "lineage": _runtime_lineage_from_public(state.lineage),
    }
    payload["state_hash"] = runtime_content_hash(payload)
    return RuntimeReplayState.model_validate(payload, strict=True)


def to_runtime_request(request: PublicCycleRequest, bundle: FoundationBundle) -> RuntimeCycleRequest:
    if request.identity != bundle.public_manifest.identity:
        raise ValueError("cycle identity does not match foundation manifest identity")
    mode = RuntimeExecutionMode(request.mode.value)
    prior_state = None
    if request.prior_state_ref is not None:
        payload = bundle.public_store.get(request.prior_state_ref)
        public_state = PublicReplayState.model_validate_json(json.dumps(payload, ensure_ascii=False))
        if public_state.identity != request.identity:
            raise ValueError("prior ReplayState identity does not match cycle request")
        if public_state.target_cycle_id != request.cycle_id:
            raise ValueError("prior ReplayState is not available for this cycle")
        prior_state = _runtime_replay_state(public_state)

    replay_bundle = None
    if mode is RuntimeExecutionMode.REPLAY:
        replay_bundle = _runtime_pointer_from_public(
            request.prior_state_ref
            if request.prior_state_ref is not None
            else request.stimulus_ref
        )

    return RuntimeCycleRequest(
        request_id=request.request_id,
        run_id=request.identity.run_id,
        snapshot_id=request.identity.snapshot_id,
        cycle_id=request.cycle_id,
        mode=mode,
        as_of_time=request.identity.as_of_time,
        logical_time=request.logical_time,
        foundation_manifest=bundle.runtime_manifest,
        foundation_manifest_ref=runtime_manifest_pointer(bundle),
        prior_state=prior_state,
        stimulus_ref=_runtime_pointer_from_public(request.stimulus_ref),
        schedule_context_ref=(
            None
            if request.schedule_context_ref is None
            else _runtime_pointer_from_public(request.schedule_context_ref)
        ),
        seed=request.seed,
        capability_flags=request.capability_flags,
        budget=request.budget,
        replay_bundle=replay_bundle,
    )


def _public_pointer_from_runtime(pointer: RuntimePointer) -> PublicPointer:
    scheme, _, location = pointer.storage_ref.partition("://")
    if not location:
        scheme, location = "memory", pointer.storage_ref
    if scheme not in {"file", "object_store", "database", "memory", "test_fixture"}:
        scheme = "memory"
    return PublicPointer(
        artifact_name=pointer.artifact_name,
        schema_id=pointer.schema_id,
        schema_version=_semver(pointer.schema_version),
        artifact_id=pointer.artifact_id,
        content_hash=pointer.content_hash,
        status=ArtifactStatus(pointer.status.value),
        storage_ref=StorageReference(scheme=scheme, location=location),
        producer_module_id=(
            pointer.producer_module_id if pointer.producer_module_id != "P3.ORCHESTRATOR" else "P3.ORCHESTRATOR"
        ),
        lineage_id=pointer.lineage_id,
        row_count=pointer.row_count,
        grain=pointer.grain,
    )


def _cycle_status(status: ExecutionStatus) -> CycleStatus:
    return {
        ExecutionStatus.READY: CycleStatus.SUCCEEDED,
        ExecutionStatus.EMPTY_VALID: CycleStatus.SUCCEEDED,
        ExecutionStatus.DEGRADED: CycleStatus.DEGRADED,
        ExecutionStatus.BLOCKED: CycleStatus.BLOCKED,
        ExecutionStatus.FAILED: CycleStatus.FAILED,
        ExecutionStatus.SKIPPED_NOT_APPLICABLE: CycleStatus.SUCCEEDED,
    }[status]


def _build_public_closure(
    request: PublicCycleRequest, closure: object
) -> tuple[PublicClosure, PublicPointer]:
    lineage = PublicLineage(
        lineage_id=closure.lineage.lineage_id,
        producer_module_id=_producer(closure.lineage.producer_module_id),
        sources=tuple(
            LineageSource(artifact_id=artifact_id, content_hash=hash_value)
            for artifact_id, hash_value in zip(
                closure.lineage.source_artifact_ids, closure.lineage.source_hashes, strict=True
            )
        ),
        transformation_ids=("runtime_closure_adapter.v2",),
    )
    base: dict[str, object] = {
        "artifact_id": closure.artifact_id, "identity": request.identity,
        "source_cycle_id": closure.source_cycle_id, "target_cycle_id": closure.target_cycle_id,
        "completed_at": closure.as_of_time,
        "foundation_manifest_ref": _public_pointer_from_runtime(closure.foundation_manifest_ref),
        "next_person_state_ref": _public_pointer_from_runtime(closure.next_person_state),
        "next_belief_state_ref": _public_pointer_from_runtime(closure.next_belief_state),
        "next_memory_state_ref": _public_pointer_from_runtime(closure.next_memory_state),
        "next_social_graph_ref": _public_pointer_from_runtime(closure.next_social_graph),
        "next_endogenous_queue_ref": _public_pointer_from_runtime(closure.next_cycle_stimulus_queue),
        "belief_commitments_ref": _public_pointer_from_runtime(closure.belief_commitment_log),
        "tool_audit_ref": _public_pointer_from_runtime(closure.tool_audit),
        "cycle_snapshot_ref": _public_pointer_from_runtime(closure.cycle_audit),
        "status": ArtifactStatus(closure.status.value),
        "issues": tuple(issue.message for issue in closure.issues),
        "lineage": lineage, "content_hash": "0" * 64,
    }
    base["content_hash"] = public_content_hash({k: v for k, v in base.items() if k != "content_hash"})
    public_closure = PublicClosure.model_validate(base, strict=True)
    pointer = PublicPointer(
        artifact_name=public_closure.artifact_name, schema_id=public_closure.schema_id,
        schema_version=public_closure.schema_version, artifact_id=public_closure.artifact_id,
        content_hash=public_closure.content_hash, status=public_closure.status,
        storage_ref=StorageReference(scheme="memory", location=f"closure/{public_closure.artifact_id}"),
        producer_module_id="P3.S26.M03", lineage_id=public_closure.lineage.lineage_id,
        available_at=request.logical_time,
    )
    return public_closure, pointer


def _build_public_replay_state(
    request: PublicCycleRequest, public_closure: PublicClosure
) -> tuple[PublicReplayState, PublicPointer]:
    source_pointers = (
        public_closure.next_person_state_ref, public_closure.next_belief_state_ref,
        public_closure.next_memory_state_ref, public_closure.next_social_graph_ref,
        public_closure.next_endogenous_queue_ref, public_closure.belief_commitments_ref,
        public_closure.foundation_manifest_ref,
    )
    lineage = PublicLineage(
        lineage_id=f"lineage-replay-{request.cycle_id}-{public_closure.target_cycle_id}",
        producer_module_id="P3.S26.M03",
        sources=tuple(LineageSource(artifact_id=p.artifact_id, content_hash=p.content_hash) for p in source_pointers),
        parent_lineage_ids=(public_closure.lineage.lineage_id,),
        transformation_ids=("cycle_closure_to_replay_state.v2",),
    )
    base: dict[str, object] = {
        "artifact_name": "replay_state", "schema_id": "p3.integration.replay_state.v2",
        "schema_version": "2.0.0",
        "artifact_id": f"replay-state-{request.identity.run_id}-{public_closure.target_cycle_id}",
        "identity": request.identity, "source_cycle_id": public_closure.source_cycle_id,
        "target_cycle_id": public_closure.target_cycle_id,
        "source": (PublicStateSource.WARMUP_CHECKPOINT
                   if request.mode is PublicExecutionMode.WARMUP_REPLAY else PublicStateSource.PRIOR_CYCLE),
        "person_state_ref": public_closure.next_person_state_ref,
        "belief_state_ref": public_closure.next_belief_state_ref,
        "memory_state_ref": public_closure.next_memory_state_ref,
        "social_graph_ref": public_closure.next_social_graph_ref,
        "pending_stimuli_ref": public_closure.next_endogenous_queue_ref,
        "belief_commitments_ref": public_closure.belief_commitments_ref,
        "foundation_manifest_ref": public_closure.foundation_manifest_ref,
        "audit_refs": (public_closure.tool_audit_ref, public_closure.cycle_snapshot_ref),
        "state_hash": "0" * 64, "lineage": lineage,
    }
    base["state_hash"] = public_content_hash({k: v for k, v in base.items() if k != "state_hash"})
    replay = PublicReplayState.model_validate(base, strict=True)
    pointer = PublicPointer(
        artifact_name=replay.artifact_name, schema_id=replay.schema_id, schema_version=replay.schema_version,
        artifact_id=replay.artifact_id, content_hash=public_content_hash(replay.model_dump(mode="json")),
        status=ArtifactStatus.READY,
        storage_ref=StorageReference(scheme="memory", location=f"replay/{replay.artifact_id}"),
        producer_module_id="P3.S26.M03", lineage_id=replay.lineage.lineage_id,
        available_at=request.logical_time,
    )
    return replay, pointer


def _cross_phase_outputs(result: RuntimeCycleResult, mode: PublicExecutionMode) -> CrossPhaseOutputs:
    if mode is not PublicExecutionMode.LIVE:
        return CrossPhaseOutputs()
    converted = tuple(_public_pointer_from_runtime(pointer) for pointer in result.p4_outputs)
    by_name = {pointer.artifact_name: pointer for pointer in converted}
    required = (
        "social_feature_panel", "evidence_tag_panel", "agent_disagreement_panel",
        "context_memory_feature_panel", "hypothesis_registry", "phase4_social_handoff_manifest",
    )
    missing = [name for name in required if name not in by_name]
    if missing:
        raise ValueError(f"runtime result is missing P4 outputs: {missing}")
    p9 = {p.artifact_name: p for p in map(_public_pointer_from_runtime, getattr(result, "p9_outputs", ()))}
    required_p9 = {"p9_evaluation_evidence_bundle", "p9_context_learning_handoff_manifest"}
    if missing_p9 := sorted(required_p9 - set(p9)):
        raise ValueError(f"runtime result is missing P9 outputs: {missing_p9}")
    variable = getattr(result, "variable_evolution_output", None)
    if variable is None:
        raise ValueError("runtime result is missing variable evolution output")
    return CrossPhaseOutputs(
        p4=P4Outputs(
            social_feature_panel_ref=by_name["social_feature_panel"],
            evidence_tag_panel_ref=by_name["evidence_tag_panel"],
            agent_disagreement_panel_ref=by_name["agent_disagreement_panel"],
            context_memory_feature_panel_ref=by_name["context_memory_feature_panel"],
            hypothesis_registry_ref=by_name["hypothesis_registry"],
            phase4_social_handoff_manifest_ref=by_name["phase4_social_handoff_manifest"],
        ),
        p9=P9Outputs(
            evaluation_evidence_bundle_ref=p9["p9_evaluation_evidence_bundle"],
            context_learning_handoff_manifest_ref=p9["p9_context_learning_handoff_manifest"],
        ),
        variable_evolution_input_manifest_ref=_public_pointer_from_runtime(variable),
    )


def _module_trace_pointer(request: PublicCycleRequest, result: RuntimeCycleResult) -> PublicPointer:
    return PublicPointer(
        artifact_name="module_trace", schema_id="p3.integration.module_trace.v2", schema_version="2.0.0",
        artifact_id=f"module-trace-{request.cycle_id}",
        content_hash=public_content_hash([entry.model_dump(mode="json") for entry in result.module_trace]),
        status=ArtifactStatus.READY,
        storage_ref=StorageReference(scheme="memory", location=f"trace/{request.cycle_id}"),
        producer_module_id="P3.ORCHESTRATOR", row_count=len(result.module_trace), grain=("module_id",),
    )


def adapt_runtime_result(
    *, request: PublicCycleRequest, result: RuntimeCycleResult, bundle: FoundationBundle
) -> tuple[PublicCycleResult, PublicClosure | None]:
    """Translate the runtime result into Contract Pack V2 without semantic loss."""
    if request.mode is PublicExecutionMode.DRY_RUN:
        status = CycleStatus.BLOCKED if result.status is ExecutionStatus.BLOCKED else CycleStatus.DRY_RUN_VALIDATED
        return PublicCycleResult(
            request_id=request.request_id, identity=request.identity, cycle_id=request.cycle_id,
            mode=request.mode, status=status, issues=tuple(issue.message for issue in result.issues),
        ), None
    if result.closure_manifest is None:
        raise ValueError("executed runtime result does not contain a closure")
    public_closure, closure_pointer = _build_public_closure(request, result.closure_manifest)
    bundle.public_store.put(closure_pointer, public_closure)
    replay_state, replay_pointer = _build_public_replay_state(request, public_closure)
    bundle.public_store.put(replay_pointer, replay_state)
    public_result = PublicCycleResult(
        request_id=request.request_id, identity=request.identity, cycle_id=request.cycle_id, mode=request.mode,
        status=_cycle_status(result.status), closure_manifest_ref=closure_pointer, next_state_ref=replay_pointer,
        checkpoint_ref=_public_pointer_from_runtime(result.closure_manifest.cycle_audit),
        audit_summary_ref=_public_pointer_from_runtime(result.closure_manifest.tool_audit),
        module_trace_ref=_module_trace_pointer(request, result),
        cross_phase_outputs=_cross_phase_outputs(result, request.mode),
        issues=tuple(issue.message for issue in result.issues),
    )
    return public_result, public_closure


__all__ = [
    "FoundationBundle",
    "adapt_runtime_result",
    "build_foundation_bundle",
    "runtime_manifest_pointer",
    "to_runtime_request",
]
