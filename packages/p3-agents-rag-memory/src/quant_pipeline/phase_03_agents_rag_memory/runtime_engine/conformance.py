from __future__ import annotations

from dataclasses import dataclass

from .errors import BoundaryValidationError
from .contracts_internal import P3CycleClosureManifest, ReplayState
from .ports import CheckpointResolverPort


@dataclass(frozen=True, slots=True)
class CheckpointResolverConformance:
    """Evidence returned after validating the external A-side checkpoint resolver."""

    run_id: str
    source_cycle_id: str
    target_cycle_id: str
    replay_state_hash: str
    verified_pointer_count: int


async def validate_checkpoint_resolver(
    resolver: CheckpointResolverPort,
    closure: P3CycleClosureManifest,
) -> CheckpointResolverConformance:
    """Prove that an A-side resolver preserves the B closure without inventing state.

    The function is a consumer-contract harness. It deliberately does not know how foundation
    stores or materializes artifacts; it only verifies the canonical result.
    """

    state = await resolver.resolve(closure)
    _validate_identity(closure, state)
    _validate_pointers(closure, state)
    _validate_lineage(closure, state)
    return CheckpointResolverConformance(
        run_id=state.run_id,
        source_cycle_id=closure.source_cycle_id,
        target_cycle_id=state.cycle_id,
        replay_state_hash=state.state_hash,
        verified_pointer_count=8,
    )


def _validate_identity(closure: P3CycleClosureManifest, state: ReplayState) -> None:
    if state.run_id != closure.run_id or state.snapshot_id != closure.snapshot_id:
        raise BoundaryValidationError("checkpoint resolver changed run or snapshot identity")
    if state.cycle_id != closure.target_cycle_id:
        raise BoundaryValidationError("checkpoint resolver did not materialize the target cycle")
    if state.as_of_time != closure.as_of_time:
        raise BoundaryValidationError("checkpoint resolver changed the cycle cutoff")
    if state.status.value in {"BLOCKED", "FAILED"}:
        raise BoundaryValidationError("checkpoint resolver returned a non-consumable ReplayState")


def _validate_pointers(closure: P3CycleClosureManifest, state: ReplayState) -> None:
    expected = {
        "person_state": closure.next_person_state,
        "belief_state": closure.next_belief_state,
        "memory_state": closure.next_memory_state,
        "social_graph": closure.next_social_graph,
        "pending_stimuli": closure.next_cycle_stimulus_queue,
        "belief_commitments": closure.belief_commitment_log,
        "resource_manifest_ref": closure.foundation_manifest_ref,
    }
    for field_name, pointer in expected.items():
        if getattr(state, field_name) != pointer:
            raise BoundaryValidationError(
                f"checkpoint resolver changed closure pointer {field_name}"
            )
    required_audits = {closure.tool_audit.artifact_id, closure.cycle_audit.artifact_id}
    observed_audits = {pointer.artifact_id for pointer in state.audit_refs}
    if not required_audits.issubset(observed_audits):
        raise BoundaryValidationError("checkpoint resolver omitted required audit pointers")


def _validate_lineage(closure: P3CycleClosureManifest, state: ReplayState) -> None:
    if closure.artifact_id not in state.lineage.source_artifact_ids:
        raise BoundaryValidationError("ReplayState lineage does not reference the closure artifact")
    if closure.content_hash not in state.lineage.source_hashes:
        raise BoundaryValidationError("ReplayState lineage does not reference the closure hash")
