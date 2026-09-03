"""Canonical ReplayState loader used by P3.S11.M03.

The loader consumes Contract Pack V2 only. It never infers missing state and
never treats a closure manifest as a state snapshot.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Protocol

from ..contracts import ArtifactPointer, ReplayState, RunIdentity, content_hash


class ArtifactPayloadResolver(Protocol):
    def get(self, pointer: ArtifactPointer) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class LoadedCycleState:
    current_person_state_panel: dict[str, Any]
    current_belief_state_panel: dict[str, Any]
    current_memory_state: dict[str, Any]
    current_social_graph: dict[str, Any]


def _materialize(
    *,
    artifact_name: str,
    pointer: ArtifactPointer,
    resolver: ArtifactPayloadResolver,
    identity: RunIdentity,
    cycle_id: str,
    logical_time: datetime,
    replay_state: ReplayState,
) -> dict[str, Any]:
    source = resolver.get(pointer)
    payload: dict[str, Any] = {
        "schema_id": f"p3.integration.{artifact_name}.v2",
        "schema_version": "2.0.0",
        "artifact_name": artifact_name,
        "artifact_id": f"{artifact_name}-{identity.run_id}-{cycle_id}",
        "run_id": identity.run_id,
        "snapshot_id": identity.snapshot_id,
        "cycle_id": cycle_id,
        "as_of_time": logical_time,
        "source_replay_state_id": replay_state.artifact_id,
        "source_artifact_id": pointer.artifact_id,
        "records": tuple(source.get("records", source.get("items", ()))),
        "lineage_id": f"lineage-{artifact_name}-{replay_state.artifact_id}",
    }
    payload["content_hash"] = content_hash(payload)
    return payload


def load_replay_state(
    *,
    replay_state: ReplayState | Mapping[str, Any],
    resolver: ArtifactPayloadResolver,
    identity: RunIdentity,
    cycle_id: str,
    logical_time: datetime,
) -> LoadedCycleState:
    state = (
        replay_state
        if isinstance(replay_state, ReplayState)
        else ReplayState.model_validate(dict(replay_state), strict=False)
    )
    if state.identity != identity:
        raise ValueError("ReplayState identity does not match current run")
    if state.target_cycle_id != cycle_id:
        raise ValueError(
            f"ReplayState targets {state.target_cycle_id}, not current cycle {cycle_id}"
        )
    if state.identity.as_of_time > logical_time:
        raise ValueError("ReplayState is newer than the current logical time")
    return LoadedCycleState(
        current_person_state_panel=_materialize(
            artifact_name="current_person_state_panel",
            pointer=state.person_state_ref,
            resolver=resolver,
            identity=identity,
            cycle_id=cycle_id,
            logical_time=logical_time,
            replay_state=state,
        ),
        current_belief_state_panel=_materialize(
            artifact_name="current_belief_state_panel",
            pointer=state.belief_state_ref,
            resolver=resolver,
            identity=identity,
            cycle_id=cycle_id,
            logical_time=logical_time,
            replay_state=state,
        ),
        current_memory_state=_materialize(
            artifact_name="current_memory_state",
            pointer=state.memory_state_ref,
            resolver=resolver,
            identity=identity,
            cycle_id=cycle_id,
            logical_time=logical_time,
            replay_state=state,
        ),
        current_social_graph=_materialize(
            artifact_name="current_social_graph",
            pointer=state.social_graph_ref,
            resolver=resolver,
            identity=identity,
            cycle_id=cycle_id,
            logical_time=logical_time,
            replay_state=state,
        ),
    )
