from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Iterable, Mapping

from pydantic import ValidationError

from .errors import (
    BootstrapLeakageError,
    CycleStateLoadError,
    S11Issue,
    WarmupReplayError,
)
from .models import (
    ArtifactRef,
    ArtifactStatus,
    BeliefStatePanel,
    CanonicalCyclePipelineConfig,
    CheckpointRecord,
    CurrentBeliefStatePanel,
    CurrentMemoryState,
    CurrentPersonStatePanel,
    CurrentSocialGraph,
    CycleKernelRequest,
    CycleKernelResult,
    CycleStateLoadRequest,
    CycleStateLoadResult,
    FoundationResourceManifest,
    InitialCycleStateSnapshot,
    InitialSocialGraphView,
    KernelExecutionStatus,
    LeakageValidationReport,
    MemoryState,
    PersonDynamicStatus,
    PersonSeedPanelView,
    PersonStatePanel,
    PersonStateRecord,
    ReplayCursor,
    ReplayInvocationMode,
    ReplayItemAudit,
    ReplayState,
    RetroPolicyPatchView,
    SocialEdgeState,
    SocialGraphState,
    StateLineage,
    StateSource,
    ValidatedInitialCycleStateSnapshot,
    WarmupCheckpointPlanView,
    WarmupEventScheduleView,
    WarmupMode,
    WarmupReplayAudit,
    WarmupReplayConfig,
)
from .ports import CheckpointStorePort, CycleKernelPort

FORBIDDEN_FIELDS = {
    "future_return", "candidate_score", "rank_score", "portfolio_weight",
    "trade_decision", "buy_sell_signal", "realized_return", "outcome_label",
    "holdout_label", "future_target",
}


def canonicalize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Mapping):
        return {str(k): canonicalize(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (tuple, list)):
        return [canonicalize(item) for item in value]
    return value


def hash_value(value: Any) -> str:
    encoded = json.dumps(canonicalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stable_id(prefix: str, *parts: object) -> str:
    return f"{prefix}-{hash_value(parts)[:20]}"


def _log(logger: Callable[[str, dict[str, object]], None] | None, event: str, **fields: object) -> None:
    if logger is not None:
        logger(event, fields)


def _artifact_ref(artifact_id: str, artifact_type: str, value: Any, schema_id: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        content_hash=hash_value(value),
        schema_id=schema_id,
        schema_version="2.0.0",
    )


class GenesisStateFactory:
    """Pure and deterministic genesis-state builder; the orchestrator only delegates to it."""

    def build(
        self,
        *,
        schedule: WarmupEventScheduleView,
        checkpoint_plan: WarmupCheckpointPlanView,
        person_seed_panel: PersonSeedPanelView,
        social_graph: InitialSocialGraphView,
        resources: FoundationResourceManifest,
        retro_patch: RetroPolicyPatchView,
    ) -> ReplayState:
        if person_seed_panel.run_id != schedule.run_id or person_seed_panel.snapshot_id != schedule.snapshot_id:
            raise WarmupReplayError([S11Issue("A3_S11_POPULATION_IDENTITY_MISMATCH", "Population identity differs from schedule")])
        if social_graph.population_hash != person_seed_panel.population_hash:
            raise WarmupReplayError([S11Issue("A3_S11_POPULATION_HASH_MISMATCH", "Social graph and person seeds use different populations")])
        person_ids = {p.person_id for p in person_seed_panel.persons}
        for edge in social_graph.records:
            if edge.source_person_id not in person_ids or edge.target_person_id not in person_ids:
                raise WarmupReplayError([S11Issue("A3_S11_ORPHAN_SOCIAL_EDGE", f"Unknown person in edge {edge.edge_id}")])

        genesis_time = min(
            schedule.schedule_start or checkpoint_plan.final_checkpoint_time,
            checkpoint_plan.final_checkpoint_time,
        )
        person_records = tuple(
            PersonStateRecord(
                person_id=seed.person_id,
                structural_profile_hash=seed.structural_profile_hash,
                representation_weight=seed.representation_weight,
                status=PersonDynamicStatus.ACTIVE,
                attention=0.5,
                fatigue=0.0,
                last_updated_at=genesis_time,
            )
            for seed in sorted(person_seed_panel.persons, key=lambda item: item.person_id)
        )
        social_records = tuple(
            SocialEdgeState(
                edge_id=edge.edge_id,
                source_person_id=edge.source_person_id,
                target_person_id=edge.target_person_id,
                relationship_type=edge.relationship_type,
                trust=edge.trust,
                strength=edge.strength,
                influence=edge.influence,
                interaction_frequency=edge.interaction_frequency,
                selection_probability=edge.selection_probability,
                domain_trust=edge.domain_trust,
                origin=edge.origin,
                valid_from=genesis_time,
                available_at=genesis_time,
            )
            for edge in sorted(social_graph.records, key=lambda item: item.edge_id)
        )
        person_panel = PersonStatePanel(records=person_records, content_hash=hash_value(person_records))
        belief_panel = BeliefStatePanel(records=(), content_hash=hash_value(()))
        memory_state = MemoryState(records=(), content_hash=hash_value(()))
        graph_state = SocialGraphState(records=social_records, content_hash=hash_value(social_records))
        cursor = ReplayCursor(
            last_completed_schedule_sequence=0,
            last_checkpoint_id=None,
            schedule_hash=schedule.schedule_hash,
            checkpoint_plan_hash=checkpoint_plan.plan_hash,
        )
        resource_ref = ArtifactRef(
            artifact_id=resources.artifact_id,
            artifact_type="p3_foundation_resource_manifest",
            content_hash=resources.manifest_hash,
            schema_id=resources.schema_id,
            schema_version=resources.schema_version,
        )
        policy_refs = tuple(
            ref for ref in (
                retro_patch.prompt_policy_ref,
                retro_patch.retrieval_policy_ref,
                retro_patch.tool_policy_ref,
            ) if ref is not None
        )
        lineage = StateLineage(
            lineage_id=stable_id("lineage-genesis", schedule.artifact_id, person_seed_panel.artifact_id, social_graph.artifact_id),
            source_artifact_ids=(schedule.artifact_id, checkpoint_plan.artifact_id, person_seed_panel.artifact_id, social_graph.artifact_id, resources.artifact_id, retro_patch.artifact_id),
            source_lineage_ids=(person_seed_panel.lineage_id, social_graph.lineage_id, retro_patch.lineage_id),
        )
        state_payload = {
            "run_id": schedule.run_id,
            "snapshot_id": schedule.snapshot_id,
            "replay_cycle_number": 0,
            "as_of_time": genesis_time,
            "population_hash": person_seed_panel.population_hash,
            "source": StateSource.GENESIS,
            "person_state": person_panel,
            "belief_state": belief_panel,
            "memory_state": memory_state,
            "social_graph": graph_state,
            "pending_stimuli": (),
            "belief_commitments": (),
            "replay_cursor": cursor,
            "resource_manifest_ref": resource_ref,
            "policy_refs": policy_refs,
            "audit_refs": (),
            "lineage": lineage,
        }
        return ReplayState(**state_payload, state_hash=hash_value(state_payload))


@dataclass(frozen=True, slots=True)
class ReplayOutputs:
    initial_cycle_state_snapshot: InitialCycleStateSnapshot
    warmup_replay_audit: WarmupReplayAudit


class WarmupReplayOrchestrator:
    def __init__(
        self,
        *,
        kernel: CycleKernelPort,
        checkpoint_store: CheckpointStorePort,
        genesis_factory: GenesisStateFactory | None = None,
        clock: Callable[[], datetime] | None = None,
        logger: Callable[[str, dict[str, object]], None] | None = None,
    ) -> None:
        self._kernel = kernel
        self._checkpoint_store = checkpoint_store
        self._genesis_factory = genesis_factory or GenesisStateFactory()
        self._clock = clock
        self._logger = logger

    async def run(
        self,
        *,
        warmup_event_schedule: object,
        warmup_checkpoint_plan: object,
        person_seed_panel: object,
        validated_initial_social_graph: object,
        active_retro_policy_patch: object,
        canonical_cycle_pipeline_config: object,
        warmup_replay_config: object,
    ) -> ReplayOutputs:
        started = time.perf_counter()
        try:
            schedule = WarmupEventScheduleView.model_validate(warmup_event_schedule)
            plan = WarmupCheckpointPlanView.model_validate(warmup_checkpoint_plan)
            seeds = PersonSeedPanelView.model_validate(person_seed_panel)
            graph = InitialSocialGraphView.model_validate(validated_initial_social_graph)
            retro = RetroPolicyPatchView.model_validate(active_retro_policy_patch)
            pipeline = CanonicalCyclePipelineConfig.model_validate(canonical_cycle_pipeline_config)
            config = WarmupReplayConfig.model_validate(warmup_replay_config)
        except ValidationError as exc:
            raise WarmupReplayError([S11Issue("A3_S11_INPUT_INVALID", str(exc))]) from exc

        _log(self._logger, "warmup_replay_started", run_id=schedule.run_id, snapshot_id=schedule.snapshot_id, item_count=len(schedule.items))
        self._validate_identity(schedule, plan, seeds, graph, retro, pipeline)
        self._validate_kernel_contract(pipeline)
        if len(schedule.items) > config.max_replay_items:
            raise WarmupReplayError([S11Issue("A3_S11_REPLAY_ITEM_LIMIT", "schedule exceeds max_replay_items")])

        invocation_mode = ReplayInvocationMode.GENESIS_ONLY if schedule.mode is WarmupMode.GENESIS_ONLY else ReplayInvocationMode.HISTORICAL_REPLAY
        if config.resume_checkpoint_id is not None:
            if not plan.resume_supported:
                raise WarmupReplayError([S11Issue("A3_S11_RESUME_NOT_SUPPORTED", "checkpoint plan disables resume")])
            state = await self._checkpoint_store.load(config.resume_checkpoint_id)
            self._validate_resume_state(state, schedule, plan, pipeline)
            invocation_mode = ReplayInvocationMode.RESUME_REPLAY
            resume_source = config.resume_checkpoint_id
        else:
            state = self._genesis_factory.build(
                schedule=schedule,
                checkpoint_plan=plan,
                person_seed_panel=seeds,
                social_graph=graph,
                resources=pipeline.foundation_resource_manifest,
                retro_patch=retro,
            )
            resume_source = None

        checkpoint_by_sequence = {item.after_schedule_sequence_number: item for item in plan.checkpoints}
        checkpoint_records: list[CheckpointRecord] = []
        item_audits: list[ReplayItemAudit] = []
        existing_checkpoint_ids: set[str] = set()
        if state.replay_cursor.last_checkpoint_id is not None:
            existing_checkpoint_ids.add(state.replay_cursor.last_checkpoint_id)

        if not schedule.items:
            planned = plan.checkpoints[0]
            state = state.model_copy(update={
                "replay_cursor": state.replay_cursor.model_copy(update={"last_checkpoint_id": planned.checkpoint_id}),
            })
            state = state.model_copy(update={"state_hash": self._rehash_state(state)})
            checkpoint_ref = await self._checkpoint_store.write(planned.checkpoint_id, state)
            checkpoint_records.append(self._checkpoint_record(planned, checkpoint_ref, state))
        else:
            for item in schedule.items:
                if item.sequence_number <= state.replay_cursor.last_completed_schedule_sequence:
                    continue
                prior_hash = state.state_hash
                request = self._build_kernel_request(
                    state=state,
                    item=item,
                    resources=pipeline.foundation_resource_manifest,
                    retro=retro,
                    config=config,
                )
                _log(self._logger, "warmup_schedule_item_started", run_id=schedule.run_id, schedule_item_id=item.schedule_item_id, sequence_number=item.sequence_number)
                result = await self._kernel.execute_cycle(request)
                state = self._validate_kernel_result(result, request, schedule, plan, pipeline, config)
                item_audits.append(ReplayItemAudit(
                    schedule_item_id=item.schedule_item_id,
                    sequence_number=item.sequence_number,
                    request_id=request.request_id,
                    logical_time=item.logical_time,
                    status=result.status.value,
                    prior_state_hash=prior_hash,
                    next_state_hash=state.state_hash,
                    module_trace=result.module_trace,
                    tool_audits=result.tool_audits,
                ))
                planned = checkpoint_by_sequence.get(item.sequence_number)
                if planned is not None:
                    if planned.checkpoint_id in existing_checkpoint_ids:
                        raise WarmupReplayError([S11Issue("A3_S11_DUPLICATE_CHECKPOINT", planned.checkpoint_id)])
                    state = state.model_copy(update={
                        "replay_cursor": state.replay_cursor.model_copy(update={"last_checkpoint_id": planned.checkpoint_id}),
                    })
                    state = state.model_copy(update={"state_hash": self._rehash_state(state)})
                    checkpoint_ref = await self._checkpoint_store.write(planned.checkpoint_id, state)
                    checkpoint_records.append(self._checkpoint_record(planned, checkpoint_ref, state))
                    existing_checkpoint_ids.add(planned.checkpoint_id)
                _log(self._logger, "warmup_schedule_item_completed", run_id=schedule.run_id, schedule_item_id=item.schedule_item_id, state_hash=state.state_hash)

        terminal_checkpoint_id = plan.final_checkpoint_id
        if state.replay_cursor.last_checkpoint_id != terminal_checkpoint_id:
            planned = next((c for c in plan.checkpoints if c.checkpoint_id == terminal_checkpoint_id), None)
            if planned is None:
                raise WarmupReplayError([S11Issue("A3_S11_FINAL_CHECKPOINT_MISSING", terminal_checkpoint_id)])
            state = state.model_copy(update={
                "replay_cursor": state.replay_cursor.model_copy(update={"last_checkpoint_id": planned.checkpoint_id}),
            })
            state = state.model_copy(update={"state_hash": self._rehash_state(state)})
            checkpoint_ref = await self._checkpoint_store.write(planned.checkpoint_id, state)
            checkpoint_records.append(self._checkpoint_record(planned, checkpoint_ref, state))
        terminal_ref = await self._checkpoint_store.write(terminal_checkpoint_id, state)

        snapshot_payload = {
            "artifact_id": stable_id("initial-state", schedule.run_id, state.state_hash, terminal_checkpoint_id),
            "run_id": schedule.run_id,
            "snapshot_id": schedule.snapshot_id,
            "evaluation_start": schedule.evaluation_start,
            "terminal_checkpoint_id": terminal_checkpoint_id,
            "terminal_checkpoint_ref": terminal_ref,
            "state": state,
            "lineage": state.lineage,
        }
        initial_snapshot = InitialCycleStateSnapshot(**snapshot_payload, content_hash=hash_value(snapshot_payload))
        audit_payload = {
            "artifact_id": stable_id("warmup-audit", schedule.run_id, schedule.schedule_hash, state.state_hash),
            "run_id": schedule.run_id,
            "snapshot_id": schedule.snapshot_id,
            "invocation_mode": invocation_mode,
            "status": ArtifactStatus.READY if all(a.status == "SUCCEEDED" for a in item_audits) else ArtifactStatus.DEGRADED,
            "schedule_hash": schedule.schedule_hash,
            "checkpoint_plan_hash": plan.plan_hash,
            "kernel_contract_version": pipeline.kernel_contract_version,
            "resource_manifest_hash": pipeline.foundation_resource_manifest.manifest_hash,
            "resume_source_checkpoint_id": resume_source,
            "item_audits": tuple(item_audits),
            "checkpoints": tuple(checkpoint_records),
            "terminal_checkpoint_id": terminal_checkpoint_id,
            "terminal_state_hash": state.state_hash,
            "metrics": {
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "schedule_item_count": len(schedule.items),
                "executed_item_count": len(item_audits),
                "checkpoint_count": len(checkpoint_records),
                "resume_count": int(resume_source is not None),
            },
            "issues": tuple(issue for audit in item_audits for issue in ()),
            "lineage_id": stable_id("lineage-replay-audit", schedule.artifact_id, plan.artifact_id, state.state_hash),
        }
        audit = WarmupReplayAudit(**audit_payload)
        _log(self._logger, "warmup_replay_completed", run_id=schedule.run_id, status=audit.status.value, terminal_state_hash=state.state_hash)
        return ReplayOutputs(initial_cycle_state_snapshot=initial_snapshot, warmup_replay_audit=audit)

    def _validate_identity(self, schedule: WarmupEventScheduleView, plan: WarmupCheckpointPlanView, seeds: PersonSeedPanelView, graph: InitialSocialGraphView, retro: RetroPolicyPatchView, pipeline: CanonicalCyclePipelineConfig) -> None:
        identities = {(schedule.run_id, schedule.snapshot_id), (plan.run_id, plan.snapshot_id), (seeds.run_id, seeds.snapshot_id), (graph.run_id, graph.snapshot_id), (retro.run_id, retro.snapshot_id), (pipeline.foundation_resource_manifest.run_id, pipeline.foundation_resource_manifest.snapshot_id)}
        if len(identities) != 1:
            raise WarmupReplayError([S11Issue("A3_S11_IDENTITY_MISMATCH", "All S11 inputs must share run_id and snapshot_id")])
        if schedule.schedule_hash != plan.schedule_hash:
            raise WarmupReplayError([S11Issue("A3_S11_SCHEDULE_PLAN_HASH_MISMATCH", "checkpoint plan does not bind the supplied schedule")])
        if schedule.mode is not plan.mode:
            raise WarmupReplayError([S11Issue("A3_S11_MODE_MISMATCH", "schedule and checkpoint plan modes differ")])
        if seeds.population_hash != graph.population_hash:
            raise WarmupReplayError([S11Issue("A3_S11_POPULATION_HASH_MISMATCH", "person seeds and social graph differ")])
        if schedule.evaluation_start != plan.evaluation_start:
            raise WarmupReplayError([S11Issue("A3_S11_EVALUATION_START_MISMATCH", "schedule and plan evaluation_start differ")])

    def _validate_kernel_contract(self, pipeline: CanonicalCyclePipelineConfig) -> None:
        if self._kernel.contract_version not in pipeline.accepted_kernel_versions:
            raise WarmupReplayError([S11Issue("A3_S11_KERNEL_VERSION_MISMATCH", f"Kernel {self._kernel.contract_version!r} not accepted")])
        if pipeline.kernel_contract_version != self._kernel.contract_version:
            raise WarmupReplayError([S11Issue("A3_S11_KERNEL_VERSION_MISMATCH", "Configured and injected kernel versions differ")])

    def _validate_resume_state(self, state: ReplayState, schedule: WarmupEventScheduleView, plan: WarmupCheckpointPlanView, pipeline: CanonicalCyclePipelineConfig) -> None:
        if state.run_id != schedule.run_id or state.snapshot_id != schedule.snapshot_id:
            raise WarmupReplayError([S11Issue("A3_S11_RESUME_IDENTITY_MISMATCH", "resume state belongs to another run")])
        if state.replay_cursor.schedule_hash != schedule.schedule_hash or state.replay_cursor.checkpoint_plan_hash != plan.plan_hash:
            raise WarmupReplayError([S11Issue("A3_S11_RESUME_HASH_MISMATCH", "resume checkpoint was produced by different schedule or plan")])
        if state.resource_manifest_ref.content_hash != pipeline.foundation_resource_manifest.manifest_hash:
            raise WarmupReplayError([S11Issue("A3_S11_RESOURCE_MANIFEST_MISMATCH", "resume checkpoint resource manifest changed")])
        if state.state_hash != self._rehash_state(state):
            raise WarmupReplayError([S11Issue("A3_S11_STATE_HASH_MISMATCH", "resume state hash is invalid")])

    def _build_kernel_request(self, *, state: ReplayState, item: Any, resources: FoundationResourceManifest, retro: RetroPolicyPatchView, config: WarmupReplayConfig) -> CycleKernelRequest:
        request_id = stable_id("kernel-request", state.run_id, item.schedule_item_id, state.state_hash, self._kernel.contract_version)
        seed = int(hash_value((config.base_seed, item.schedule_item_id, state.state_hash))[:16], 16)
        return CycleKernelRequest(
            request_id=request_id,
            run_id=state.run_id,
            snapshot_id=state.snapshot_id,
            cycle_id=f"warmup-{item.sequence_number:08d}",
            mode="WARMUP_REPLAY",
            logical_time=item.logical_time,
            prior_state=state,
            schedule_item=item,
            resource_manifest=resources,
            retro_policy_patch=retro,
            seed=seed,
        )

    def _validate_kernel_result(self, result: CycleKernelResult, request: CycleKernelRequest, schedule: WarmupEventScheduleView, plan: WarmupCheckpointPlanView, pipeline: CanonicalCyclePipelineConfig, config: WarmupReplayConfig) -> ReplayState:
        if result.request_id != request.request_id:
            raise WarmupReplayError([S11Issue("A3_S11_KERNEL_REQUEST_ID_MISMATCH", "kernel result request_id differs")])
        if result.status is KernelExecutionStatus.FAILED:
            raise WarmupReplayError([S11Issue("A3_S11_REPLAY_ITEM_FAILED", request.schedule_item.schedule_item_id)])
        if result.status is KernelExecutionStatus.DEGRADED and config.stop_on_kernel_degraded:
            raise WarmupReplayError([S11Issue("A3_S11_KERNEL_DEGRADED_BLOCKED", request.schedule_item.schedule_item_id)])
        if result.emitted_p4_outputs or result.emitted_p9_outputs:
            raise WarmupReplayError([S11Issue("A3_S11_OUTPUT_AUTHORITY_VIOLATION", "warm-up kernel emitted P4/P9 output")])
        if not result.module_trace:
            raise WarmupReplayError([S11Issue("A3_S11_KERNEL_TRACE_EMPTY", "kernel must emit module trace")])
        expected_time = request.logical_time
        for trace in result.module_trace:
            if trace.as_of_time != expected_time:
                raise WarmupReplayError([S11Issue("A3_S11_TRACE_TIME_MISMATCH", trace.module_id)])
        next_state = result.next_state
        if next_state.run_id != request.run_id or next_state.snapshot_id != request.snapshot_id:
            raise WarmupReplayError([S11Issue("A3_S11_KERNEL_STATE_IDENTITY_MISMATCH", "kernel changed run identity")])
        if next_state.as_of_time != request.logical_time:
            raise WarmupReplayError([S11Issue("A3_S11_KERNEL_STATE_TIME_MISMATCH", "next state must be at schedule logical_time")])
        if next_state.population_hash != request.prior_state.population_hash:
            raise WarmupReplayError([S11Issue("A3_S11_POPULATION_DRIFT", "kernel changed frozen population")])
        if next_state.replay_cycle_number != request.prior_state.replay_cycle_number + 1:
            raise WarmupReplayError([S11Issue("A3_S11_REPLAY_CYCLE_GAP", "kernel did not increment replay cycle exactly once")])
        expected_cursor = request.schedule_item.sequence_number
        cursor = next_state.replay_cursor.model_copy(update={
            "last_completed_schedule_sequence": expected_cursor,
            "schedule_hash": schedule.schedule_hash,
            "checkpoint_plan_hash": plan.plan_hash,
        })
        state = next_state.model_copy(update={
            "source": StateSource.WARMUP_CHECKPOINT,
            "replay_cursor": cursor,
        })
        state = state.model_copy(update={"state_hash": self._rehash_state(state)})
        return state

    def _checkpoint_record(self, planned: Any, checkpoint_ref: ArtifactRef, state: ReplayState) -> CheckpointRecord:
        return CheckpointRecord(
            checkpoint_id=planned.checkpoint_id,
            checkpoint_ref=checkpoint_ref,
            after_schedule_sequence_number=planned.after_schedule_sequence_number,
            logical_time=planned.logical_time,
            state_hash=state.state_hash,
            previous_checkpoint_id=planned.previous_checkpoint_id,
            final=planned.final,
        )

    def _rehash_state(self, state: ReplayState) -> str:
        payload = state.model_dump(mode="json", exclude={"state_hash"})
        return hash_value(payload)


class BootstrapLeakageGuard:
    """Compatibility facade delegating to typed leakage-validation components."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None, logger: Callable[[str, dict[str, object]], None] | None = None) -> None:
        from .leakage_validation import BootstrapLeakageValidationPipeline

        self._pipeline = BootstrapLeakageValidationPipeline(clock=clock, logger=logger)

    def validate(self, *, initial_cycle_state_snapshot: object, validated_warmup_history: object, warmup_replay_audit: object) -> ValidatedInitialCycleStateSnapshot:
        return self._pipeline.validate(
            initial_cycle_state_snapshot=initial_cycle_state_snapshot,
            validated_warmup_history=validated_warmup_history,
            warmup_replay_audit=warmup_replay_audit,
        )


class CycleStateLoader:
    """Compatibility facade delegating to typed source-resolution components."""

    def __init__(self, *, logger: Callable[[str, dict[str, object]], None] | None = None) -> None:
        from .state_loading import CycleStateLoadingPipeline

        self._pipeline = CycleStateLoadingPipeline(logger=logger)

    def load(self, request: object) -> CycleStateLoadResult:
        return self._pipeline.load(request)
