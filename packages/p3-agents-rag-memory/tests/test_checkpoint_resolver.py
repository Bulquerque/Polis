from __future__ import annotations

from datetime import UTC, datetime

from quant_pipeline.phase_03_agents_rag_memory.integration import CheckpointResolver
from quant_pipeline.phase_03_agents_rag_memory.integration.pointers import artifact_pointer
from quant_pipeline.phase_03_agents_rag_memory.shared.contracts import (
    LineageRecord,
    P3CycleClosureManifest,
    ReadinessStatus,
    StateSource,
    content_hash,
)


def _pointer(name: str, character: str):
    return artifact_pointer(
        name,
        {
            "schema_id": f"{name}.v1",
            "schema_version": "1.0.0",
            "artifact_id": name,
            "content_hash": character * 64,
            "status": "READY",
        },
        producer_module_id="RUNTIME",
    )


def test_closure_materializes_replay_state_without_copying_payloads() -> None:
    payload = {
        "artifact_id": "closure-live-000001",
        "run_id": "run-1",
        "snapshot_id": "snapshot-1",
        "cycle_id": "live-000001",
        "completed_at": datetime(2026, 7, 28, 12, tzinfo=UTC),
        "foundation_manifest_ref": _pointer("foundation_manifest", "1"),
        "next_person_state_ref": _pointer("next_person_state", "2"),
        "next_belief_state_ref": _pointer("next_belief_state", "3"),
        "next_memory_state_ref": _pointer("next_memory_state", "4"),
        "next_social_graph_ref": _pointer("next_social_graph", "5"),
        "next_endogenous_queue_ref": _pointer("next_endogenous_queue", "6"),
        "belief_commitments_ref": _pointer("belief_commitments", "7"),
        "audit_summary_ref": _pointer("audit_summary", "8"),
        "available_from_cycle": "live-000002",
        "status": ReadinessStatus.READY,
        "content_hash": "0" * 64,
        "lineage": LineageRecord(lineage_id="lineage-closure"),
    }
    payload["content_hash"] = content_hash({k: v for k, v in payload.items() if k != "content_hash"})
    closure = P3CycleClosureManifest.model_validate(payload, strict=True)
    state = CheckpointResolver().resolve(closure)
    assert state.source is StateSource.PRIOR_CYCLE
    assert state.available_from_cycle == "live-000002"
    assert state.person_state_ref == closure.next_person_state_ref
    assert state.pending_stimuli_ref == closure.next_endogenous_queue_ref
