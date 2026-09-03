"""Typed state-resolution and materialization components for P3.S11.M03."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import ValidationError

from .errors import CycleStateLoadError, S11Issue
from .models import (
    CurrentBeliefStatePanel,
    CurrentMemoryState,
    CurrentPersonStatePanel,
    CurrentSocialGraph,
    CycleStateLoadRequest,
    CycleStateLoadResult,
    ReplayState,
)


def _canonicalize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Mapping):
        return {str(k): _canonicalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonicalize(item) for item in value]
    return value


def _hash_value(value: Any) -> str:
    encoded = json.dumps(_canonicalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stable_id(prefix: str, *parts: object) -> str:
    return f"{prefix}-{_hash_value(parts)[:20]}"


@dataclass(frozen=True, slots=True)
class ResolvedStateSource:
    state: ReplayState
    source_artifact_id: str
    source_lineage_id: str
    source_kind: Literal["GENESIS", "PRIOR_CYCLE"]


class CycleStateRequestParser:
    def parse(self, request: object) -> CycleStateLoadRequest:
        try:
            return CycleStateLoadRequest.model_validate(request)
        except ValidationError as exc:
            raise CycleStateLoadError([S11Issue("A3_S11_STATE_SOURCE_INVALID", str(exc))]) from exc


class ReplayStateResolver:
    """Resolve exactly one authorized source without materializing any output."""

    def resolve(self, request: CycleStateLoadRequest) -> ResolvedStateSource:
        initial = request.validated_initial_cycle_state_snapshot
        prior = request.prior_cycle_state_snapshot
        if initial is not None:
            if request.current_cycle_number != 1:
                raise CycleStateLoadError([S11Issue("A3_S11_INITIAL_STATE_ONLY_CYCLE_ONE", "initial state can only feed cycle 1")])
            if initial.schema_version not in request.accepted_initial_schema_versions:
                raise CycleStateLoadError([S11Issue("A3_S11_STATE_SCHEMA_INCOMPATIBLE", initial.schema_version)])
            return ResolvedStateSource(initial.source_snapshot.state, initial.artifact_id, initial.lineage.lineage_id, "GENESIS")
        assert prior is not None
        if prior.schema_version not in request.accepted_prior_schema_versions:
            raise CycleStateLoadError([S11Issue("A3_S11_STATE_SCHEMA_INCOMPATIBLE", prior.schema_version)])
        if prior.available_from_cycle != request.current_cycle_number or prior.cycle_number + 1 != request.current_cycle_number:
            raise CycleStateLoadError([S11Issue("A3_S11_CYCLE_GAP", "prior state is not from N-1")])
        return ResolvedStateSource(prior.state, prior.artifact_id, prior.lineage.lineage_id, "PRIOR_CYCLE")


class ReplayStateIntegrityValidator:
    """Validate identity, temporal order, hash and cross-family referential integrity."""

    def validate(self, source: ResolvedStateSource, request: CycleStateLoadRequest) -> None:
        state = source.state
        issues: list[S11Issue] = []
        if state.run_id != request.current_run_id or state.snapshot_id != request.current_snapshot_id:
            issues.append(S11Issue("A3_S11_STATE_IDENTITY_MISMATCH", "state source belongs to another run"))
        if state.as_of_time > request.current_as_of:
            issues.append(S11Issue("A3_S11_STATE_FROM_FUTURE", "source state is after current_as_of"))
        if state.state_hash != _hash_value(state.model_dump(mode="json", exclude={"state_hash"})):
            issues.append(S11Issue("A3_S11_STATE_HASH_MISMATCH", "source state hash is invalid"))
        person_ids = [record.person_id for record in state.person_state.records]
        if not person_ids or len(person_ids) != len(set(person_ids)):
            issues.append(S11Issue("A3_S11_PERSON_STATE_INVALID", "person IDs must be unique and non-empty"))
        known = set(person_ids)
        for record in state.belief_state.records:
            if record.person_id not in known:
                issues.append(S11Issue("A3_S11_ORPHAN_BELIEF", record.belief_id))
        for record in state.memory_state.records:
            if record.person_id not in known:
                issues.append(S11Issue("A3_S11_ORPHAN_MEMORY", record.memory_id))
        for edge in state.social_graph.records:
            if edge.source_person_id not in known or edge.target_person_id not in known:
                issues.append(S11Issue("A3_S11_ORPHAN_SOCIAL_EDGE", edge.edge_id))
        for commitment in state.belief_commitments:
            if commitment.person_id not in known:
                issues.append(S11Issue("A3_S11_ORPHAN_COMMITMENT", commitment.commitment_id))
        if issues:
            raise CycleStateLoadError(issues)


class CurrentStateMaterializer:
    def materialize(self, source: ResolvedStateSource, request: CycleStateLoadRequest) -> CycleStateLoadResult:
        state = source.state
        lineage_id = _stable_id("lineage-current-state", source.source_lineage_id, request.current_cycle_id, state.state_hash)
        common = {
            "run_id": request.current_run_id,
            "snapshot_id": request.current_snapshot_id,
            "cycle_id": request.current_cycle_id,
            "cycle_number": request.current_cycle_number,
            "as_of_time": request.current_as_of,
            "source_state_hash": state.state_hash,
            "lineage_id": lineage_id,
        }
        def payload(kind: str, records: object) -> dict[str, object]:
            return {**common, "artifact_id": _stable_id(kind, source.source_artifact_id, request.current_cycle_id), "records": records}
        person = payload("current-person", state.person_state.records)
        belief = payload("current-belief", state.belief_state.records)
        memory = payload("current-memory", state.memory_state.records)
        social = payload("current-social", state.social_graph.records)
        return CycleStateLoadResult(
            person_state=CurrentPersonStatePanel(**person, content_hash=_hash_value(person)),
            belief_state=CurrentBeliefStatePanel(**belief, content_hash=_hash_value(belief)),
            memory_state=CurrentMemoryState(**memory, content_hash=_hash_value(memory)),
            social_graph=CurrentSocialGraph(**social, content_hash=_hash_value(social)),
        )


class GenesisStateMaterializer(CurrentStateMaterializer):
    """Named boundary for cycle-one materialization; it does not invent state."""


class CycleStateLoadingPipeline:
    def __init__(self, *, logger: Callable[[str, dict[str, object]], None] | None = None) -> None:
        self._logger = logger
        self._parser = CycleStateRequestParser()
        self._resolver = ReplayStateResolver()
        self._validator = ReplayStateIntegrityValidator()
        self._current = CurrentStateMaterializer()
        self._genesis = GenesisStateMaterializer()

    def load(self, request: object) -> CycleStateLoadResult:
        parsed = self._parser.parse(request)
        source = self._resolver.resolve(parsed)
        self._validator.validate(source, parsed)
        materializer = self._genesis if source.source_kind == "GENESIS" else self._current
        result = materializer.materialize(source, parsed)
        if self._logger:
            self._logger("cycle_state_materialized", {"run_id": parsed.current_run_id, "cycle_id": parsed.current_cycle_id, "source_state_hash": source.state.state_hash, "source_kind": source.source_kind})
        return result
