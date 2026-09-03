from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_03_agents_rag_memory.contracts import (
    ArtifactPointer,
    ArtifactStatus,
    BudgetLimits,
    CapabilityFlags,
    CycleKernelRequest,
    ExecutionMode,
    RunIdentity,
    StorageReference,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.warmup_memory.replay import WarmupCycleRequestBuilder


def _identity() -> RunIdentity:
    return RunIdentity(
        run_id="run",
        snapshot_id="snapshot",
        as_of_time=datetime(2026, 7, 1, tzinfo=UTC),
        pipeline_version="V14.1-RC4.1",
        architecture_revision="P3-FINAL",
    )


def _placeholder(name: str, character: str) -> ArtifactPointer:
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


def test_warmup_request_is_reference_only_and_safe() -> None:
    request = WarmupCycleRequestBuilder().build(
        request_id="warmup-request-1",
        identity=_identity(),
        cycle_id="warmup-000001",
        logical_time=datetime(2026, 7, 1, tzinfo=UTC),
        foundation_manifest_ref=_placeholder("p3_foundation_runtime_manifest", "1"),
        prior_state_ref=_placeholder("replay_state", "2"),
        stimulus_ref=_placeholder("stimulus_panel", "3"),
        schedule_context_ref=_placeholder("cognitive_cycle_schedule", "4"),
        seed=42,
        budget=BudgetLimits(max_retrieval_calls=4),
    )
    assert request.mode is ExecutionMode.WARMUP_REPLAY
    assert request.capability_flags.allow_live_providers is False
    assert request.capability_flags.emit_p4_outputs is False
    assert request.capability_flags.emit_p9_outputs is False
    assert request.prior_state_ref.artifact_name == "replay_state"


def test_replay_rejects_live_providers() -> None:
    with pytest.raises(ValidationError):
        CycleKernelRequest(
            request_id="replay-request",
            identity=_identity(),
            cycle_id="replay-live-000001",
            mode=ExecutionMode.REPLAY,
            logical_time=datetime(2026, 7, 1, tzinfo=UTC),
            foundation_manifest_ref=_placeholder("p3_foundation_runtime_manifest", "1"),
            prior_state_ref=_placeholder("replay_state", "2"),
            stimulus_ref=_placeholder("stimulus_panel", "3"),
            seed=1,
            capability_flags=CapabilityFlags(
                allow_live_providers=True,
                require_frozen_provider_responses=False,
            ),
            budget=BudgetLimits(),
        )
