from __future__ import annotations

from dataclasses import dataclass

from .contracts_internal import (
    ArtifactPointer,
    ExecutionStatus,
    FoundationRuntimeManifest,
    LineageRecord,
    P3CycleClosureManifest,
    RuntimeIssue,
    content_hash,
)
from .identity import stable_id


@dataclass(frozen=True, slots=True)
class ClosurePointers:
    next_person_state: ArtifactPointer
    next_belief_state: ArtifactPointer
    next_memory_state: ArtifactPointer
    next_social_graph: ArtifactPointer
    next_cycle_stimulus_queue: ArtifactPointer
    belief_commitment_log: ArtifactPointer
    tool_audit: ArtifactPointer
    cycle_audit: ArtifactPointer


def build_cycle_closure_manifest(
    *,
    foundation_manifest: FoundationRuntimeManifest,
    foundation_manifest_ref: ArtifactPointer,
    source_cycle_id: str,
    target_cycle_id: str,
    pointers: ClosurePointers,
    status: ExecutionStatus = ExecutionStatus.READY,
    issues: tuple[RuntimeIssue, ...] = (),
) -> P3CycleClosureManifest:
    """Create the reference-based cycle-to-state checkpoint contract without duplicating state."""

    _validate_foundation_reference(foundation_manifest, foundation_manifest_ref)
    artifact_id = stable_id(
        "p3-cycle-closure",
        foundation_manifest.run_id,
        source_cycle_id,
        target_cycle_id,
    )
    source_pointers = _source_pointers(foundation_manifest_ref, pointers)
    lineage = _build_lineage(artifact_id, source_pointers)
    values = _closure_values(
        foundation_manifest=foundation_manifest,
        foundation_manifest_ref=foundation_manifest_ref,
        artifact_id=artifact_id,
        source_cycle_id=source_cycle_id,
        target_cycle_id=target_cycle_id,
        pointers=pointers,
        lineage=lineage,
        status=status,
        issues=issues,
    )
    return P3CycleClosureManifest(**values, content_hash=content_hash(values))


def _validate_foundation_reference(
    manifest: FoundationRuntimeManifest,
    pointer: ArtifactPointer,
) -> None:
    expected = {
        "artifact_id": manifest.artifact_id,
        "schema_id": manifest.schema_id,
        "schema_version": manifest.schema_version,
        "content_hash": manifest.content_hash,
    }
    for field_name, expected_value in expected.items():
        if getattr(pointer, field_name) != expected_value:
            raise ValueError(f"foundation manifest reference {field_name} does not match manifest")


def _source_pointers(
    foundation_manifest_ref: ArtifactPointer,
    pointers: ClosurePointers,
) -> tuple[ArtifactPointer, ...]:
    return (
        foundation_manifest_ref,
        pointers.next_person_state,
        pointers.next_belief_state,
        pointers.next_memory_state,
        pointers.next_social_graph,
        pointers.next_cycle_stimulus_queue,
        pointers.belief_commitment_log,
        pointers.tool_audit,
        pointers.cycle_audit,
    )


def _build_lineage(
    artifact_id: str,
    source_pointers: tuple[ArtifactPointer, ...],
) -> LineageRecord:
    return LineageRecord(
        lineage_id=stable_id("lineage-cycle-closure", artifact_id),
        producer_module_id="P3.S26.M03",
        source_artifact_ids=tuple(pointer.artifact_id for pointer in source_pointers),
        source_hashes=tuple(pointer.content_hash for pointer in source_pointers),
    )


def _closure_values(
    *,
    foundation_manifest: FoundationRuntimeManifest,
    foundation_manifest_ref: ArtifactPointer,
    artifact_id: str,
    source_cycle_id: str,
    target_cycle_id: str,
    pointers: ClosurePointers,
    lineage: LineageRecord,
    status: ExecutionStatus,
    issues: tuple[RuntimeIssue, ...],
) -> dict[str, object]:
    return {
        "artifact_name": "p3_cycle_closure_manifest",
        "schema_id": "p3.integration.cycle_closure_manifest.v1",
        "schema_version": "1.0.0",
        "artifact_id": artifact_id,
        "run_id": foundation_manifest.run_id,
        "snapshot_id": foundation_manifest.snapshot_id,
        "source_cycle_id": source_cycle_id,
        "target_cycle_id": target_cycle_id,
        "as_of_time": foundation_manifest.as_of_time,
        "lineage": lineage,
        "foundation_manifest_ref": foundation_manifest_ref,
        "next_person_state": pointers.next_person_state,
        "next_belief_state": pointers.next_belief_state,
        "next_memory_state": pointers.next_memory_state,
        "next_social_graph": pointers.next_social_graph,
        "next_cycle_stimulus_queue": pointers.next_cycle_stimulus_queue,
        "belief_commitment_log": pointers.belief_commitment_log,
        "tool_audit": pointers.tool_audit,
        "cycle_audit": pointers.cycle_audit,
        "status": status,
        "issues": issues,
    }
