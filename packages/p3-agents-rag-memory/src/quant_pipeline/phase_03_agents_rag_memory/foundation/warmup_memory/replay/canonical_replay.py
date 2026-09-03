"""Contract Pack V2 adapters for the canonical replay representation."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ....contracts import ReplayState, RunIdentity
from ....orchestration.replay_loader import load_replay_state

_FORBIDDEN = frozenset({
    "future_return", "candidate_score", "rank_score", "portfolio_weight",
    "trade_decision", "buy_sell_signal", "realized_return", "outcome_label",
    "holdout_label", "future_target",
})


def is_canonical_replay(value: object) -> bool:
    return isinstance(value, ReplayState) or (
        isinstance(value, Mapping) and value.get("schema_id") == "p3.integration.replay_state.v2"
    )


def _iter_mappings(value: object):
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _iter_mappings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _iter_mappings(child)


class CanonicalReplayLeakageValidator:
    def validate(self, replay_value: object, audit_value: object, context: Mapping[str, Any]) -> dict[str, Any]:
        replay = replay_value if isinstance(replay_value, ReplayState) else ReplayState.model_validate(dict(replay_value), strict=False)
        resolver = context.get("canonical_artifact_store")
        if resolver is None or not callable(getattr(resolver, "get", None)):
            raise ValueError("canonical leakage validation requires context.canonical_artifact_store")
        audit = audit_value if isinstance(audit_value, Mapping) else {}
        if audit and str(audit.get("status", "")) not in {"READY", "DEGRADED"}:
            raise ValueError("warm-up replay audit is not consumable")
        terminal_ref = audit.get("terminal_state_ref") if audit else None
        if isinstance(terminal_ref, Mapping) and terminal_ref.get("artifact_id") != replay.artifact_id:
            raise ValueError("warm-up audit terminal state differs from supplied ReplayState")
        pointers = (
            replay.person_state_ref, replay.belief_state_ref, replay.memory_state_ref,
            replay.social_graph_ref, replay.pending_stimuli_ref, replay.belief_commitments_ref,
            *replay.audit_refs,
        )
        for pointer in pointers:
            if pointer.available_at is not None and pointer.available_at > replay.identity.as_of_time:
                raise ValueError(f"{pointer.artifact_name} became available after the replay cutoff")
            payload = resolver.get(pointer)
            self._validate_payload(payload, cutoff=replay.identity.as_of_time, artifact_name=pointer.artifact_name)
        return replay.model_dump(mode="json")

    def _validate_payload(self, payload: object, *, cutoff: datetime, artifact_name: str) -> None:
        for row in _iter_mappings(payload):
            forbidden = _FORBIDDEN.intersection(str(key) for key in row)
            if forbidden:
                raise ValueError(f"{artifact_name} contains forbidden future/outcome fields: {sorted(forbidden)}")
            for field in ("available_at", "as_of", "as_of_time", "logical_time"):
                raw = row.get(field)
                if not isinstance(raw, str):
                    continue
                observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if observed > cutoff:
                    raise ValueError(f"{artifact_name}.{field}={observed.isoformat()} exceeds cutoff {cutoff.isoformat()}")


class CanonicalReplayStateLoader:
    def load(self, replay_value: object, context: Mapping[str, Any]) -> dict[str, Any]:
        resolver = context.get("canonical_artifact_store")
        if resolver is None or not callable(getattr(resolver, "get", None)):
            raise ValueError("canonical ReplayState loading requires context.canonical_artifact_store")
        identity = RunIdentity(
            run_id=str(context["current_run_id"]),
            snapshot_id=str(context["current_snapshot_id"]),
            as_of_time=context["run_as_of_time"],
            pipeline_version=str(context.get("pipeline_version", "V14.1-RC4.1")),
            architecture_revision=str(context.get("architecture_revision", "P3-FINAL")),
        )
        result = load_replay_state(
            replay_state=replay_value,
            resolver=resolver,
            identity=identity,
            cycle_id=str(context["current_cycle_id"]),
            logical_time=context["current_as_of"],
        )
        return {
            "current_person_state_panel": result.current_person_state_panel,
            "current_belief_state_panel": result.current_belief_state_panel,
            "current_memory_state": result.current_memory_state,
            "current_social_graph": result.current_social_graph,
        }
