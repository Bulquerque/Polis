from __future__ import annotations

from datetime import UTC, datetime

from quant_pipeline.phase_03_agents_rag_memory.contracts import (
    ArtifactPointer,
    ArtifactStatus,
    LineageRecord,
    LineageSource,
    ReplayState,
    RunIdentity,
    StateSource,
    StorageReference,
    content_hash,
)
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S11_M03_cycle_state_loader import run_module
from quant_pipeline.phase_03_agents_rag_memory.orchestration.artifact_store import CanonicalArtifactStore


def _put(store: CanonicalArtifactStore, name: str, records: list[dict[str, object]]) -> ArtifactPointer:
    payload = {"schema_id": f"{name}.v2", "schema_version": "2.0.0", "records": records}
    pointer = ArtifactPointer(
        artifact_name=name,
        schema_id=f"{name}.v2",
        schema_version="2.0.0",
        artifact_id=f"artifact-{name}",
        content_hash=content_hash(payload),
        status=ArtifactStatus.READY,
        storage_ref=StorageReference(scheme="memory", location=name),
        producer_module_id="P3.S26.M03",
        row_count=len(records),
    )
    store.put(pointer, payload)
    return pointer


def test_s11_loader_materializes_canonical_replay_state() -> None:
    store = CanonicalArtifactStore()
    person = _put(store, "validated_next_person_state_panel", [{"person_id": "p1"}])
    belief = _put(store, "next_belief_state_panel", [{"person_id": "p1", "belief": 0.6}])
    memory = _put(store, "next_memory_state", [{"memory_id": "m1", "person_id": "p1"}])
    graph = _put(store, "next_social_graph", [{"edge_id": "e1"}])
    queue = _put(store, "next_cycle_endogenous_stimulus_queue", [])
    commitments = _put(store, "belief_outcome_commitment_log", [])
    foundation = _put(store, "p3_foundation_runtime_manifest", [])
    identity = RunIdentity(
        run_id="run-1",
        snapshot_id="snapshot-1",
        as_of_time=datetime(2026, 7, 1, tzinfo=UTC),
        pipeline_version="V14.1-RC4.1",
        architecture_revision="P3-FINAL",
    )
    lineage = LineageRecord(
        lineage_id="lineage-replay",
        producer_module_id="P3.S26.M03",
        sources=tuple(
            LineageSource(artifact_id=p.artifact_id, content_hash=p.content_hash)
            for p in (person, belief, memory, graph, queue, commitments, foundation)
        ),
    )
    base = {
        "artifact_name": "replay_state",
        "schema_id": "p3.integration.replay_state.v2",
        "schema_version": "2.0.0",
        "artifact_id": "replay-state-cycle-1",
        "identity": identity,
        "source_cycle_id": "cycle-1",
        "target_cycle_id": "cycle-2",
        "source": StateSource.PRIOR_CYCLE,
        "person_state_ref": person,
        "belief_state_ref": belief,
        "memory_state_ref": memory,
        "social_graph_ref": graph,
        "pending_stimuli_ref": queue,
        "belief_commitments_ref": commitments,
        "foundation_manifest_ref": foundation,
        "audit_refs": (),
        "state_hash": "0" * 64,
        "lineage": lineage,
    }
    base["state_hash"] = content_hash({k: v for k, v in base.items() if k != "state_hash"})
    replay = ReplayState.model_validate(base, strict=True)

    outputs = run_module(
        {
            "validated_initial_cycle_state_snapshot": None,
            "prior_cycle_state_snapshot": replay.model_dump(mode="python"),
        },
        {
            "canonical_artifact_store": store,
            "current_run_id": "run-1",
            "current_snapshot_id": "snapshot-1",
            "current_cycle_id": "cycle-2",
            "current_cycle_number": 2,
            "current_as_of": datetime(2026, 7, 2, tzinfo=UTC),
            "run_as_of_time": datetime(2026, 7, 1, tzinfo=UTC),
            "architecture_revision": "P3-FINAL",
        },
    )
    assert outputs["current_person_state_panel"]["records"] == ({"person_id": "p1"},)
    assert outputs["current_belief_state_panel"]["records"][0]["belief"] == 0.6
    assert outputs["current_memory_state"]["source_replay_state_id"] == "replay-state-cycle-1"
