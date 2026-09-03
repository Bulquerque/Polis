"""Canonical warm-up client for the public CycleKernel V2 boundary."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Protocol

from ....contracts import (
    ArtifactPointer,
    BudgetLimits,
    CapabilityFlags,
    CycleKernelRequest,
    CycleKernelResult,
    ExecutionMode,
    RunIdentity,
)


class CycleKernelPort(Protocol):
    async def execute_cycle(self, request: CycleKernelRequest) -> CycleKernelResult:
        ...


class WarmupCycleRequestBuilder:
    """Build reference-only warm-up requests with no embedded runtime state."""

    def build(
        self,
        *,
        request_id: str,
        identity: RunIdentity,
        cycle_id: str,
        logical_time: datetime,
        foundation_manifest_ref: ArtifactPointer,
        prior_state_ref: ArtifactPointer,
        stimulus_ref: ArtifactPointer,
        schedule_context_ref: ArtifactPointer | None,
        seed: int,
        budget: BudgetLimits,
    ) -> CycleKernelRequest:
        return CycleKernelRequest(
            request_id=request_id,
            identity=identity,
            cycle_id=cycle_id,
            mode=ExecutionMode.WARMUP_REPLAY,
            logical_time=logical_time,
            foundation_manifest_ref=foundation_manifest_ref,
            prior_state_ref=prior_state_ref,
            stimulus_ref=stimulus_ref,
            schedule_context_ref=schedule_context_ref,
            seed=seed,
            capability_flags=CapabilityFlags(
                allow_live_providers=False,
                allow_tool_execution=False,
                emit_p4_outputs=False,
                emit_p9_outputs=False,
                emit_variable_evolution=False,
                require_frozen_provider_responses=True,
            ),
            budget=budget,
        )


class WarmupCycleClient:
    """Invoke the same canonical kernel used by LIVE and REPLAY modes."""

    def __init__(self, kernel: CycleKernelPort) -> None:
        self._kernel = kernel

    async def execute(self, request: CycleKernelRequest) -> CycleKernelResult:
        result = await self._kernel.execute_cycle(request)
        if result.request_id != request.request_id:
            raise ValueError("kernel result request_id mismatch")
        if result.cycle_id != request.cycle_id:
            raise ValueError("kernel result cycle_id mismatch")
        if result.cross_phase_outputs.p4 is not None or result.cross_phase_outputs.p9 is not None:
            raise ValueError("warm-up kernel may not emit P4 or P9 outputs")
        return result


def _mapping(value: object, name: str) -> dict[str, object]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping or Pydantic model")
    return dict(value)


def _pointer_from_legacy_ref(
    value: object,
    *,
    artifact_name: str,
    producer_module_id: str,
    available_at: datetime,
) -> ArtifactPointer:
    payload = _mapping(value, artifact_name)
    pointer_payload = {
        "artifact_name": artifact_name,
        "schema_id": str(
            payload.get("schema_id")
            or payload.get("artifact_type")
            or f"p3.{artifact_name}.v1"
        ),
        "schema_version": str(payload.get("schema_version") or "1.0.0"),
        "artifact_id": str(payload["artifact_id"]),
        "content_hash": str(payload["content_hash"]),
        "status": "READY",
        "storage_ref": {
            "scheme": "memory",
            "location": f"warmup/{payload['artifact_id']}",
        },
        "producer_module_id": producer_module_id,
        "available_at": available_at.isoformat(),
    }
    return ArtifactPointer.model_validate_json(
        json.dumps(pointer_payload, ensure_ascii=False)
    )


class CanonicalWarmupReplayService:
    """Run S11 warm-up through the same public kernel used by live cycles.

    The service is intentionally reference-only.  It expects the foundation
    manifest and genesis/prior ReplayState to have already been persisted in
    the canonical artifact store.  Every schedule item is executed through
    ``CycleKernelPort`` and yields a persisted ReplayState for the next item.
    """

    def __init__(self, *, kernel: CycleKernelPort, artifact_store: object) -> None:
        if not callable(getattr(artifact_store, "get", None)):
            raise ValueError("artifact_store must provide get(pointer)")
        self._client = WarmupCycleClient(kernel)
        self._store = artifact_store

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
    ) -> dict[str, object]:
        del person_seed_panel, validated_initial_social_graph, active_retro_policy_patch
        schedule = _mapping(warmup_event_schedule, "warmup_event_schedule")
        plan = _mapping(warmup_checkpoint_plan, "warmup_checkpoint_plan")
        pipeline = _mapping(canonical_cycle_pipeline_config, "canonical_cycle_pipeline_config")
        replay_config = _mapping(warmup_replay_config, "warmup_replay_config")

        if pipeline.get("run_identity") is not None:
            identity = RunIdentity.model_validate_json(
                json.dumps(pipeline["run_identity"], ensure_ascii=False)
            )
        else:
            identity = RunIdentity(
                run_id=str(schedule["run_id"]),
                snapshot_id=str(schedule["snapshot_id"]),
                as_of_time=datetime.fromisoformat(
                    str(schedule["as_of"]).replace("Z", "+00:00")
                ),
                pipeline_version=str(
                    pipeline.get("pipeline_version", "V14.1-RC4.1")
                ),
                architecture_revision=str(
                    pipeline.get("architecture_revision", "P3-FINAL")
                ),
            )
        if identity.run_id != str(schedule["run_id"]) or identity.snapshot_id != str(
            schedule["snapshot_id"]
        ):
            raise ValueError("warm-up schedule identity differs from canonical run identity")
        foundation_ref = ArtifactPointer.model_validate_json(json.dumps(pipeline["foundation_manifest_ref"], ensure_ascii=False))
        prior_ref = ArtifactPointer.model_validate_json(json.dumps(pipeline["genesis_replay_state_ref"], ensure_ascii=False))
        budget_payload = replay_config.get(
            "budget",
            {
                "max_llm_calls": 0,
                "max_tool_calls": 0,
                "max_retrieval_calls": 0,
                "max_total_tokens": 24000,
            },
        )
        budget = BudgetLimits.model_validate_json(
            json.dumps(budget_payload, ensure_ascii=False)
        )
        schedule_context_ref = (
            ArtifactPointer.model_validate_json(
                json.dumps(pipeline["schedule_context_ref"], ensure_ascii=False)
            )
            if pipeline.get("schedule_context_ref") is not None
            else None
        )

        item_results: list[dict[str, object]] = []
        items = sorted(
            schedule.get("items", []),
            key=lambda item: int(_mapping(item, "schedule_item")["sequence_number"]),
        )
        base_seed = int(replay_config.get("base_seed", 0))
        for raw_item in items:
            item = _mapping(raw_item, "schedule_item")
            logical_time = datetime.fromisoformat(str(item["logical_time"]).replace("Z", "+00:00"))
            event_ref = _mapping(item.get("event_ref") or {}, "schedule_item.event_ref")
            payload_ref = event_ref.get("payload_ref")
            if payload_ref is None:
                payload_ref = pipeline.get("heartbeat_stimulus_ref")
            if payload_ref is None:
                raise ValueError(
                    f"schedule item {item.get('schedule_item_id')} has no stimulus payload ref"
                )
            stimulus_ref = _pointer_from_legacy_ref(
                payload_ref,
                artifact_name="warmup_stimulus",
                producer_module_id="P3.S10.M01",
                available_at=logical_time,
            )
            cycle_id = f"warmup-{int(item['sequence_number']):08d}"
            request = WarmupCycleRequestBuilder().build(
                request_id=f"warmup-request-{identity.run_id}-{cycle_id}",
                identity=identity,
                cycle_id=cycle_id,
                logical_time=logical_time,
                foundation_manifest_ref=foundation_ref,
                prior_state_ref=prior_ref,
                stimulus_ref=stimulus_ref,
                schedule_context_ref=schedule_context_ref,
                seed=base_seed + int(item["sequence_number"]),
                budget=budget,
            )
            result = await self._client.execute(request)
            if result.next_state_ref is None:
                raise ValueError("warm-up kernel did not produce next_state_ref")
            prior_ref = result.next_state_ref
            item_results.append(
                {
                    "schedule_item_id": str(item["schedule_item_id"]),
                    "sequence_number": int(item["sequence_number"]),
                    "request_id": request.request_id,
                    "cycle_id": cycle_id,
                    "status": result.status.value,
                    "next_state_ref": prior_ref.model_dump(mode="json"),
                }
            )

        final_state_payload = self._store.get(prior_ref)
        audit = {
            "schema_id": "warmup_replay_audit.v3",
            "schema_version": "3.0.0",
            "run_id": identity.run_id,
            "snapshot_id": identity.snapshot_id,
            "schedule_hash": schedule.get("schedule_hash"),
            "checkpoint_plan_hash": plan.get("plan_hash"),
            "executed_item_count": len(item_results),
            "terminal_state_ref": prior_ref.model_dump(mode="json"),
            "items": item_results,
            "status": "READY",
        }
        return {
            "initial_cycle_state_snapshot": final_state_payload,
            "warmup_replay_audit": audit,
        }
