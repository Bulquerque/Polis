from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_pipeline.phase_03_agents_rag_memory.contracts import (
    ArtifactPointer,
    ArtifactStatus,
    BudgetLimits,
    CapabilityFlags,
    CycleKernelRequest,
    ExecutionMode,
    StorageReference,
    content_hash,
)
from quant_pipeline.phase_03_agents_rag_memory.orchestration.boundary import (
    adapt_runtime_result,
    build_foundation_bundle,
    to_runtime_request,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime_engine.closure import (
    ClosurePointers,
    build_cycle_closure_manifest,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime_engine.contracts_internal import (
    ArtifactPointer as RuntimePointer,
    ExecutionStatus,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime_engine.foundation_consumer import FoundationManifestConsumer
from quant_pipeline.phase_03_agents_rag_memory.runtime_engine.kernel import CapabilityExecution, CycleKernel
from quant_pipeline.phase_03_agents_rag_memory.runtime_engine.testing import RecordingCapability




class _StaticRuntimeRepository:
    async def read_json(self, pointer):
        return {
            "schema_id": pointer.schema_id,
            "schema_version": pointer.schema_version,
            "artifact_id": pointer.artifact_id,
            "artifact_name": pointer.artifact_name,
            "records": [],
            "content_hash": pointer.content_hash,
        }

def _public_pointer(name: str, character: str = "a") -> ArtifactPointer:
    return ArtifactPointer(
        artifact_name=name,
        schema_id=f"p3.integration.{name}.v2",
        schema_version="2.0.0",
        artifact_id=f"artifact-{name}",
        content_hash=character * 64,
        status=ArtifactStatus.READY,
        storage_ref=StorageReference(scheme="memory", location=name),
        producer_module_id="P3.ORCHESTRATOR",
    )


def _runtime_pointer(name: str, producer: str, character: str) -> RuntimePointer:
    return RuntimePointer(
        artifact_name=name,
        schema_id=f"p3.runtime.{name}.v1",
        schema_version="1.0.0",
        artifact_id=f"artifact:{name}",
        content_hash=character * 64,
        storage_ref=f"memory://{name}",
        producer_module_id=producer,
        status=ExecutionStatus.READY,
    )


def _bundle(foundation_views):
    identity = foundation_views["governance"].identity
    return build_foundation_bundle(
        identity=identity,
        governance=foundation_views["governance"],
        population=foundation_views["population"],
        social_graph=foundation_views["social_graph"],
        state=foundation_views["state"],
        knowledge=foundation_views["knowledge"],
        memory=foundation_views["memory"],
        tooling=foundation_views["tooling"],
        capabilities=("foundation", "runtime", "warmup", "replay"),
        population_coverage_ratio=0.875,
    )


def _request(
    bundle,
    mode: ExecutionMode,
    *,
    cycle_id: str = "cycle-0001",
    prior_state_ref: ArtifactPointer | None = None,
    schedule_context_ref: ArtifactPointer | None = None,
) -> CycleKernelRequest:
    return CycleKernelRequest(
        request_id=f"request-{mode.value.lower()}-{cycle_id}",
        identity=bundle.public_manifest.identity,
        cycle_id=cycle_id,
        mode=mode,
        logical_time=bundle.public_manifest.identity.as_of_time,
        foundation_manifest_ref=ArtifactPointer(
            artifact_name=bundle.public_manifest.artifact_name,
            schema_id=bundle.public_manifest.schema_id,
            schema_version=bundle.public_manifest.schema_version,
            artifact_id=bundle.public_manifest.artifact_id,
            content_hash=bundle.public_manifest.content_hash,
            status=bundle.public_manifest.status,
            storage_ref=StorageReference(scheme="memory", location="foundation-manifest"),
            producer_module_id="P3.ORCHESTRATOR",
            lineage_id=bundle.public_manifest.lineage.lineage_id,
        ),
        prior_state_ref=prior_state_ref,
        stimulus_ref=_public_pointer("stimulus_panel", "b"),
        schedule_context_ref=schedule_context_ref,
        seed=7,
        capability_flags=CapabilityFlags(
            allow_live_providers=mode is ExecutionMode.LIVE,
            allow_tool_execution=mode is ExecutionMode.LIVE,
            emit_p4_outputs=mode is ExecutionMode.LIVE,
            emit_p9_outputs=mode is ExecutionMode.LIVE,
            emit_variable_evolution=mode is ExecutionMode.LIVE,
            require_frozen_provider_responses=mode is not ExecutionMode.LIVE,
        ),
        budget=BudgetLimits(max_llm_calls=2, max_tool_calls=2, max_retrieval_calls=4, max_total_tokens=4096),
    )


def _closure(bundle, request, *, target_cycle_id: str = "cycle-0002"):
    refs = ClosurePointers(
        next_person_state=_runtime_pointer("validated_next_person_state_panel", "P3.S26.M03", "1"),
        next_belief_state=_runtime_pointer("next_belief_state_panel", "P3.S26.M03", "2"),
        next_memory_state=_runtime_pointer("next_memory_state", "P3.S26.M01", "3"),
        next_social_graph=_runtime_pointer("next_social_graph", "P3.S25.M03", "4"),
        next_cycle_stimulus_queue=_runtime_pointer("next_cycle_endogenous_stimulus_queue", "P3.S26.M02", "5"),
        belief_commitment_log=_runtime_pointer("belief_outcome_commitment_log", "P3.S22.M03", "6"),
        tool_audit=_runtime_pointer("tool_call_audit_panel", "P3.S21.M03", "7"),
        cycle_audit=_runtime_pointer("cycle_state_snapshot_out", "P3.S26.M03", "8"),
    )
    runtime_request = to_runtime_request(request, bundle)
    return build_cycle_closure_manifest(
        foundation_manifest=bundle.runtime_manifest,
        foundation_manifest_ref=runtime_request.foundation_manifest_ref,
        source_cycle_id=request.cycle_id,
        target_cycle_id=target_cycle_id,
        pointers=refs,
    )


@pytest.mark.asyncio
async def test_real_foundation_views_are_consumed_by_runtime(foundation_views) -> None:
    bundle = _bundle(foundation_views)
    context = await FoundationManifestConsumer(bundle.runtime_resolver).resolve(bundle.runtime_manifest)
    assert bundle.public_manifest.schema_version == "2.0.0"
    assert len(bundle.public_manifest.view_pointers) == 7
    assert context.population.records
    assert context.population.records[0].person_id == foundation_views["population"].records[0].person_id
    assert context.governance.run_id == bundle.public_manifest.identity.run_id


@pytest.mark.asyncio
async def test_dry_run_validates_without_execution(foundation_views) -> None:
    bundle = _bundle(foundation_views)
    capabilities = [RecordingCapability(CapabilityExecution()) for _ in range(5)]
    kernel = CycleKernel(
        foundation_resolver=FoundationManifestConsumer(bundle.runtime_resolver),
        context_capability=capabilities[0],
        cognition_capability=capabilities[1],
        closure_capability=capabilities[2],
        analytics_capability=capabilities[3],
        products_capability=capabilities[4],
    )
    public_request = _request(bundle, ExecutionMode.DRY_RUN)
    internal_result = await kernel.execute_cycle(to_runtime_request(public_request, bundle))
    public_result, closure = adapt_runtime_result(request=public_request, result=internal_result, bundle=bundle)
    assert closure is None
    assert public_result.status.value == "DRY_RUN_VALIDATED"
    assert all(cap.calls == ["validate:DRY_RUN"] for cap in capabilities)


@pytest.mark.asyncio
async def test_warmup_uses_runtime_kernel_without_external_outputs(foundation_views) -> None:
    bundle = _bundle(foundation_views)
    public_request = _request(bundle, ExecutionMode.WARMUP_REPLAY)
    closure = _closure(bundle, public_request)
    products = RecordingCapability(CapabilityExecution())
    kernel = CycleKernel(
        foundation_resolver=FoundationManifestConsumer(bundle.runtime_resolver),
        context_capability=RecordingCapability(CapabilityExecution()),
        cognition_capability=RecordingCapability(CapabilityExecution()),
        closure_capability=RecordingCapability(CapabilityExecution(closure_manifest=closure)),
        products_capability=products,
    )
    internal_result = await kernel.execute_cycle(to_runtime_request(public_request, bundle))
    public_result, public_closure = adapt_runtime_result(request=public_request, result=internal_result, bundle=bundle)
    assert public_closure is not None
    assert public_result.next_state_ref is not None
    assert public_result.next_state_ref.artifact_name == "replay_state"
    assert public_result.next_state_ref.artifact_id != public_result.closure_manifest_ref.artifact_id
    assert public_result.cross_phase_outputs.p4 is None
    assert products.calls == []


@pytest.mark.asyncio
async def test_live_exposes_every_cross_phase_output(foundation_views) -> None:
    bundle = _bundle(foundation_views)
    public_request = _request(bundle, ExecutionMode.LIVE)
    closure = _closure(bundle, public_request)
    p4_names = (
        "social_feature_panel",
        "evidence_tag_panel",
        "agent_disagreement_panel",
        "context_memory_feature_panel",
        "hypothesis_registry",
        "phase4_social_handoff_manifest",
    )
    products = CapabilityExecution(
        p4_outputs=tuple(_runtime_pointer(name, "P3.S30.M04", str(index + 1)) for index, name in enumerate(p4_names)),
        p9_outputs=(
            _runtime_pointer("p9_evaluation_evidence_bundle", "P3.S31.M01", "a"),
            _runtime_pointer("p9_context_learning_handoff_manifest", "P3.S31.M02", "b"),
        ),
        variable_evolution_output=_runtime_pointer("variable_evolution_input_manifest", "P3.S30.M05", "c"),
    )
    kernel = CycleKernel(
        foundation_resolver=FoundationManifestConsumer(bundle.runtime_resolver),
        context_capability=RecordingCapability(CapabilityExecution()),
        cognition_capability=RecordingCapability(CapabilityExecution()),
        closure_capability=RecordingCapability(CapabilityExecution(closure_manifest=closure)),
        analytics_capability=RecordingCapability(CapabilityExecution()),
        products_capability=RecordingCapability(products),
    )
    internal_result = await kernel.execute_cycle(to_runtime_request(public_request, bundle))
    public_result, public_closure = adapt_runtime_result(request=public_request, result=internal_result, bundle=bundle)
    assert public_closure is not None
    assert public_result.cross_phase_outputs.p4 is not None
    assert public_result.cross_phase_outputs.p9 is not None
    assert public_result.cross_phase_outputs.variable_evolution_input_manifest_ref is not None
    assert public_result.cross_phase_outputs.p9.evaluation_evidence_bundle_ref.artifact_name == "p9_evaluation_evidence_bundle"


@pytest.mark.asyncio
async def test_request_semantics_and_replay_state_survive_two_cycles(foundation_views) -> None:
    bundle = _bundle(foundation_views)
    schedule_ref = _public_pointer("cognitive_cycle_schedule", "d")
    first_request = _request(
        bundle,
        ExecutionMode.WARMUP_REPLAY,
        schedule_context_ref=schedule_ref,
    )
    first_closure = _closure(bundle, first_request, target_cycle_id="cycle-0002")
    first_kernel = CycleKernel(
        foundation_resolver=FoundationManifestConsumer(bundle.runtime_resolver),
        context_capability=RecordingCapability(CapabilityExecution()),
        cognition_capability=RecordingCapability(CapabilityExecution()),
        closure_capability=RecordingCapability(CapabilityExecution(closure_manifest=first_closure)),
    )
    internal_first_request = to_runtime_request(first_request, bundle)
    assert internal_first_request.stimulus_ref.artifact_name == "stimulus_panel"
    assert internal_first_request.schedule_context_ref is not None
    assert internal_first_request.schedule_context_ref.artifact_name == "cognitive_cycle_schedule"
    assert internal_first_request.budget.max_total_tokens == 4096
    assert internal_first_request.capability_flags.require_frozen_provider_responses is True

    first_internal_result = await first_kernel.execute_cycle(internal_first_request)
    first_result, _ = adapt_runtime_result(
        request=first_request,
        result=first_internal_result,
        bundle=bundle,
    )
    assert first_result.next_state_ref is not None

    second_request = _request(
        bundle,
        ExecutionMode.WARMUP_REPLAY,
        cycle_id="cycle-0002",
        prior_state_ref=first_result.next_state_ref,
        schedule_context_ref=schedule_ref,
    )
    internal_second_request = to_runtime_request(second_request, bundle)
    assert internal_second_request.prior_state is not None
    assert internal_second_request.prior_state.cycle_id == "cycle-0001"
    assert internal_second_request.prior_state.pending_stimuli.artifact_name == "next_cycle_endogenous_stimulus_queue"

    second_closure = _closure(bundle, second_request, target_cycle_id="cycle-0003")
    second_kernel = CycleKernel(
        foundation_resolver=FoundationManifestConsumer(bundle.runtime_resolver),
        context_capability=RecordingCapability(CapabilityExecution()),
        cognition_capability=RecordingCapability(CapabilityExecution()),
        closure_capability=RecordingCapability(CapabilityExecution(closure_manifest=second_closure)),
    )
    second_internal_result = await second_kernel.execute_cycle(internal_second_request)
    second_result, _ = adapt_runtime_result(
        request=second_request,
        result=second_internal_result,
        bundle=bundle,
    )
    assert second_result.next_state_ref is not None
    second_payload = bundle.public_store.get(second_result.next_state_ref)
    assert second_payload["source_cycle_id"] == "cycle-0002"
    assert second_payload["target_cycle_id"] == "cycle-0003"


@pytest.mark.asyncio
async def test_s11_module_uses_public_kernel_and_persists_replay_state(foundation_views) -> None:
    """S11.M01 must use the same public kernel boundary as live execution."""

    from quant_pipeline.phase_03_agents_rag_memory.foundation.warmup_memory.replay.integration import (
        CanonicalWarmupReplayService,
    )
    from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S11_M01_warmup_replay_orchestrator import (
        run_module,
    )
    from quant_pipeline.phase_03_agents_rag_memory.orchestration.public_kernel import (
        PublicCycleKernel,
    )

    bundle = _bundle(foundation_views)

    # Produce the canonical state available to the first warm-up item.
    bootstrap_request = _request(
        bundle,
        ExecutionMode.WARMUP_REPLAY,
        cycle_id="genesis-cycle",
    )
    bootstrap_closure = _closure(
        bundle,
        bootstrap_request,
        target_cycle_id="warmup-00000001",
    )
    bootstrap_kernel = CycleKernel(
        foundation_resolver=FoundationManifestConsumer(bundle.runtime_resolver),
        context_capability=RecordingCapability(CapabilityExecution()),
        cognition_capability=RecordingCapability(CapabilityExecution()),
        closure_capability=RecordingCapability(
            CapabilityExecution(closure_manifest=bootstrap_closure)
        ),
    )
    runtime_repository = _StaticRuntimeRepository()
    bootstrap_result = await PublicCycleKernel(
        kernel=bootstrap_kernel,
        foundation_bundle=bundle,
        runtime_repository=runtime_repository,
    ).execute_cycle(bootstrap_request)
    assert bootstrap_result.next_state_ref is not None

    warmup_request = _request(
        bundle,
        ExecutionMode.WARMUP_REPLAY,
        cycle_id="warmup-00000001",
        prior_state_ref=bootstrap_result.next_state_ref,
    )
    warmup_closure = _closure(
        bundle,
        warmup_request,
        target_cycle_id="warmup-00000002",
    )
    warmup_kernel = CycleKernel(
        foundation_resolver=FoundationManifestConsumer(bundle.runtime_resolver),
        context_capability=RecordingCapability(CapabilityExecution()),
        cognition_capability=RecordingCapability(CapabilityExecution()),
        closure_capability=RecordingCapability(
            CapabilityExecution(closure_manifest=warmup_closure)
        ),
    )
    service = CanonicalWarmupReplayService(
        kernel=PublicCycleKernel(
            kernel=warmup_kernel,
            foundation_bundle=bundle,
            runtime_repository=runtime_repository,
        ),
        artifact_store=bundle.public_store,
    )
    foundation_ref = warmup_request.foundation_manifest_ref
    inputs = {
        "warmup_event_schedule": {
            "run_id": bundle.public_manifest.identity.run_id,
            "snapshot_id": bundle.public_manifest.identity.snapshot_id,
            "as_of": bundle.public_manifest.identity.as_of_time.isoformat(),
            "schedule_hash": "schedule-hash",
            "items": [
                {
                    "schedule_item_id": "item-0001",
                    "sequence_number": 1,
                    "logical_time": bundle.public_manifest.identity.as_of_time.isoformat(),
                    "event_ref": {
                        "payload_ref": {
                            "artifact_id": "warmup-stimulus-0001",
                            "artifact_type": "warmup_stimulus",
                            "content_hash": "e" * 64,
                            "schema_id": "p3.warmup.stimulus.v1",
                            "schema_version": "1.0.0",
                        }
                    },
                }
            ],
        },
        "warmup_checkpoint_plan": {"plan_hash": "checkpoint-plan-hash"},
        "person_seed_panel": {},
        "validated_initial_social_graph": {},
        "active_retro_policy_patch": {},
        "canonical_cycle_pipeline_config": {
            "pipeline_version": "V14.1-RC4.1",
            "architecture_revision": "P3-FINAL",
            "run_identity": bundle.public_manifest.identity.model_dump(mode="json"),
            "foundation_manifest_ref": foundation_ref.model_dump(mode="json"),
            "genesis_replay_state_ref": bootstrap_result.next_state_ref.model_dump(
                mode="json"
            ),
        },
        "warmup_replay_config": {
            "base_seed": 17,
            "budget": {
                "max_llm_calls": 0,
                "max_tool_calls": 0,
                "max_retrieval_calls": 0,
                "max_total_tokens": 4096,
            },
        },
    }
    output = await run_module(
        inputs,
        {"warmup_replay_orchestrator": service},
    )
    final_state = output["initial_cycle_state_snapshot"]
    assert final_state["schema_id"] == "p3.integration.replay_state.v2"
    assert final_state["source_cycle_id"] == "warmup-00000001"
    assert final_state["target_cycle_id"] == "warmup-00000002"
    assert output["warmup_replay_audit"]["executed_item_count"] == 1

    from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S11_M02_bootstrap_leakage_guard import (
        run_module as run_leakage_guard,
    )
    from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S11_M03_cycle_state_loader import (
        run_module as run_state_loader,
    )

    guarded = run_leakage_guard(
        {
            "initial_cycle_state_snapshot": final_state,
            "validated_warmup_history": {},
            "warmup_replay_audit": output["warmup_replay_audit"],
        },
        {"canonical_artifact_store": bundle.public_store},
    )
    loaded = run_state_loader(
        {
            "validated_initial_cycle_state_snapshot": guarded[
                "validated_initial_cycle_state_snapshot"
            ],
            "prior_cycle_state_snapshot": None,
        },
        {
            "canonical_artifact_store": bundle.public_store,
            "current_run_id": bundle.public_manifest.identity.run_id,
            "current_snapshot_id": bundle.public_manifest.identity.snapshot_id,
            "current_cycle_id": "warmup-00000002",
            "current_cycle_number": 2,
            "current_as_of": bundle.public_manifest.identity.as_of_time,
            "run_as_of_time": bundle.public_manifest.identity.as_of_time,
            "pipeline_version": bundle.public_manifest.identity.pipeline_version,
            "architecture_revision": bundle.public_manifest.identity.architecture_revision,
        },
    )
    assert loaded["current_person_state_panel"]["source_artifact_id"] == (
        final_state["person_state_ref"]["artifact_id"]
    )
    assert loaded["current_memory_state"]["source_replay_state_id"] == final_state[
        "artifact_id"
    ]
