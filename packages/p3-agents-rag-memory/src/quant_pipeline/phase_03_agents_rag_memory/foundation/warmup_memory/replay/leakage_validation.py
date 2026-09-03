"""Typed components for P3.S11.M02 bootstrap leakage validation."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from .errors import BootstrapLeakageError, S11Issue
from .models import (
    InitialCycleStateSnapshot,
    LeakageValidationReport,
    StateLineage,
    ValidatedInitialCycleStateSnapshot,
    WarmupReplayAudit,
)

FORBIDDEN_FIELDS = frozenset({
    "future_return", "candidate_score", "rank_score", "portfolio_weight",
    "trade_decision", "buy_sell_signal", "realized_return", "outcome_label",
    "holdout_label", "future_target",
})


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
class WarmupHistoryIdentity:
    artifact_id: str
    run_id: str
    snapshot_id: str
    evaluation_start: datetime
    lineage_id: str


@dataclass(frozen=True, slots=True)
class BootstrapLeakageInputs:
    snapshot: InitialCycleStateSnapshot
    history: WarmupHistoryIdentity
    audit: WarmupReplayAudit


@dataclass(frozen=True, slots=True)
class BootstrapLeakageFacts:
    issues: tuple[S11Issue, ...]
    max_available_at: datetime
    canonical_module_count: int
    tool_audit_count: int
    person_count: int


class BootstrapLeakageInputParser:
    """Parse the three public artifacts into typed, minimal validation inputs."""

    def parse(
        self,
        *,
        initial_cycle_state_snapshot: object,
        validated_warmup_history: object,
        warmup_replay_audit: object,
    ) -> BootstrapLeakageInputs:
        try:
            snapshot = InitialCycleStateSnapshot.model_validate(initial_cycle_state_snapshot)
            audit = WarmupReplayAudit.model_validate(warmup_replay_audit)
        except ValidationError as exc:
            raise BootstrapLeakageError([S11Issue("A3_S11_M02_INPUT_INVALID", str(exc))]) from exc
        history = self._parse_history(validated_warmup_history)
        return BootstrapLeakageInputs(snapshot=snapshot, history=history, audit=audit)

    def _parse_history(self, value: object) -> WarmupHistoryIdentity:
        if not isinstance(value, Mapping):
            raise BootstrapLeakageError([S11Issue("A3_S11_HISTORY_INVALID", "validated_warmup_history must be an object")])
        required = {"schema_id", "schema_version", "artifact_id", "run_id", "snapshot_id", "evaluation_start", "lineage"}
        missing = sorted(required - set(value))
        if missing:
            raise BootstrapLeakageError([S11Issue("A3_S11_HISTORY_INVALID", f"missing fields: {missing}")])
        if value["schema_id"] != "validated_warmup_history.v1" or value["schema_version"] != "1.0.0":
            raise BootstrapLeakageError([S11Issue("A3_S11_HISTORY_SCHEMA_INCOMPATIBLE", "S11 requires validated_warmup_history.v1/1.0.0")])
        raw_dt = value["evaluation_start"]
        if isinstance(raw_dt, str):
            raw_dt = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
        if not isinstance(raw_dt, datetime) or raw_dt.tzinfo is None:
            raise BootstrapLeakageError([S11Issue("A3_S11_HISTORY_TIME_INVALID", "evaluation_start must be timezone-aware")])
        lineage = value["lineage"]
        lineage_id = lineage.get("lineage_id") if isinstance(lineage, Mapping) else None
        if not isinstance(lineage_id, str) or not lineage_id:
            raise BootstrapLeakageError([S11Issue("A3_S11_HISTORY_LINEAGE_INVALID", "history lineage_id missing")])
        return WarmupHistoryIdentity(
            artifact_id=str(value["artifact_id"]),
            run_id=str(value["run_id"]),
            snapshot_id=str(value["snapshot_id"]),
            evaluation_start=raw_dt.astimezone(UTC),
            lineage_id=lineage_id,
        )


class BootstrapIdentityValidator:
    def validate(self, inputs: BootstrapLeakageInputs) -> list[S11Issue]:
        snapshot, history, audit = inputs.snapshot, inputs.history, inputs.audit
        issues: list[S11Issue] = []
        if snapshot.run_id != audit.run_id or snapshot.snapshot_id != audit.snapshot_id:
            issues.append(S11Issue("A3_S11_AUDIT_IDENTITY_MISMATCH", "snapshot and audit identities differ"))
        if history.run_id != snapshot.run_id or history.snapshot_id != snapshot.snapshot_id:
            issues.append(S11Issue("A3_S11_HISTORY_IDENTITY_MISMATCH", "history and snapshot identities differ"))
        return issues


class BootstrapTemporalReferenceValidator:
    """Validate all record and audit availability against the terminal state cutoff."""

    def validate(self, inputs: BootstrapLeakageInputs) -> tuple[list[S11Issue], list[datetime], int, int]:
        snapshot, history, audit = inputs.snapshot, inputs.history, inputs.audit
        state = snapshot.state
        issues: list[S11Issue] = []
        max_times: list[datetime] = [state.as_of_time]
        if state.as_of_time >= history.evaluation_start or snapshot.evaluation_start != history.evaluation_start:
            issues.append(S11Issue("A3_S11_EVALUATION_OVERLAP", "bootstrap state must be strictly before evaluation_start"))
        for record in state.person_state.records:
            max_times.append(record.last_updated_at)
            if record.last_updated_at > state.as_of_time:
                issues.append(S11Issue("A3_S11_FUTURE_PERSON_STATE", record.person_id))
        for record in state.belief_state.records:
            max_times.append(record.available_at)
            if record.available_at > state.as_of_time:
                issues.append(S11Issue("A3_S11_FUTURE_BELIEF", record.belief_id))
        for record in state.memory_state.records:
            max_times.extend((record.created_at, record.available_at))
            if record.available_at > state.as_of_time:
                issues.append(S11Issue("A3_S11_FUTURE_MEMORY", record.memory_id))
        for edge in state.social_graph.records:
            max_times.extend((edge.valid_from, edge.available_at))
            if edge.available_at > state.as_of_time:
                issues.append(S11Issue("A3_S11_FUTURE_SOCIAL_EDGE", edge.edge_id))
        for commitment in state.belief_commitments:
            max_times.append(commitment.committed_at)
            if commitment.committed_at > state.as_of_time:
                issues.append(S11Issue("A3_S11_FUTURE_COMMITMENT", commitment.commitment_id))
        trace_count = tool_count = 0
        for item in audit.item_audits:
            trace_count += len(item.module_trace)
            tool_count += len(item.tool_audits)
            for trace in item.module_trace:
                max_times.append(trace.as_of_time)
                if trace.as_of_time > state.as_of_time:
                    issues.append(S11Issue("A3_S11_FUTURE_MODULE_TRACE", trace.module_id))
            for tool in item.tool_audits:
                max_times.append(tool.available_at)
                if tool.available_at > state.as_of_time:
                    issues.append(S11Issue("A3_S11_FUTURE_TOOL_RESULT", tool.tool_call_id))
        return issues, max_times, trace_count, tool_count


class BootstrapStateIntegrityValidator:
    def validate(self, inputs: BootstrapLeakageInputs) -> tuple[list[S11Issue], int]:
        snapshot, audit = inputs.snapshot, inputs.audit
        state = snapshot.state
        issues: list[S11Issue] = []
        if state.state_hash != _hash_value(state.model_dump(mode="json", exclude={"state_hash"})):
            issues.append(S11Issue("A3_S11_STATE_HASH_MISMATCH", "state hash does not match content"))
        if audit.terminal_state_hash != state.state_hash or audit.terminal_checkpoint_id != snapshot.terminal_checkpoint_id:
            issues.append(S11Issue("A3_S11_AUDIT_TERMINAL_MISMATCH", "audit does not bind terminal snapshot"))
        person_ids = {record.person_id for record in state.person_state.records}
        if not person_ids:
            issues.append(S11Issue("A3_S11_EMPTY_POPULATION_STATE", "person state is empty"))
        if len(person_ids) != len(state.person_state.records):
            issues.append(S11Issue("A3_S11_DUPLICATE_PERSON_STATE", "person state contains duplicate persons"))
        for record in state.belief_state.records:
            if record.person_id not in person_ids:
                issues.append(S11Issue("A3_S11_ORPHAN_BELIEF", record.belief_id))
        for record in state.memory_state.records:
            if record.person_id not in person_ids:
                issues.append(S11Issue("A3_S11_ORPHAN_MEMORY", record.memory_id))
        for edge in state.social_graph.records:
            if edge.source_person_id not in person_ids or edge.target_person_id not in person_ids:
                issues.append(S11Issue("A3_S11_ORPHAN_SOCIAL_EDGE", edge.edge_id))
        for commitment in state.belief_commitments:
            if commitment.person_id not in person_ids:
                issues.append(S11Issue("A3_S11_ORPHAN_COMMITMENT", commitment.commitment_id))
        if state.lineage.holdout_refs or snapshot.lineage.holdout_refs:
            issues.append(S11Issue("A3_S11_HOLDOUT_ACCESS", "holdout refs present in state lineage"))
        issues.extend(ForbiddenFieldScanner().scan(_canonicalize({"snapshot": snapshot, "audit": audit})))
        return issues, len(person_ids)


class ForbiddenFieldScanner:
    def scan(self, value: object, path: str = "root") -> list[S11Issue]:
        issues: list[S11Issue] = []
        if isinstance(value, Mapping):
            for key, nested in value.items():
                current = f"{path}.{key}"
                if str(key) in FORBIDDEN_FIELDS:
                    issues.append(S11Issue("A3_S11_FORBIDDEN_FIELD", str(key), current))
                issues.extend(self.scan(nested, current))
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                issues.extend(self.scan(nested, f"{path}[{index}]"))
        return issues


class LeakageValidationReportAssembler:
    def build(
        self,
        *,
        inputs: BootstrapLeakageInputs,
        max_times: list[datetime],
        trace_count: int,
        tool_count: int,
        person_count: int,
        checked_at: datetime,
    ) -> ValidatedInitialCycleStateSnapshot:
        snapshot, history, audit = inputs.snapshot, inputs.history, inputs.audit
        state = snapshot.state
        report = LeakageValidationReport(
            status="PASS",
            checked_at=checked_at,
            evaluation_start=history.evaluation_start,
            max_available_at=max(max_times),
            canonical_module_count=trace_count,
            tool_audit_count=tool_count,
            person_count=person_count,
            belief_count=len(state.belief_state.records),
            memory_count=len(state.memory_state.records),
            social_edge_count=len(state.social_graph.records),
            checks=(
                "point_in_time_integrity", "state_hash_integrity", "audit_binding",
                "population_integrity", "canonical_module_trace", "tool_audit_temporality",
                "forbidden_field_absence", "holdout_absence",
            ),
        )
        payload = {
            "artifact_id": _stable_id("validated-initial-state", snapshot.artifact_id, report.model_dump(mode="json")),
            "run_id": snapshot.run_id,
            "snapshot_id": snapshot.snapshot_id,
            "source_snapshot": snapshot,
            "validation_report": report,
            "lineage": StateLineage(
                lineage_id=_stable_id("lineage-validated-initial", snapshot.lineage.lineage_id, audit.lineage_id),
                source_artifact_ids=(snapshot.artifact_id, audit.artifact_id, history.artifact_id),
                source_lineage_ids=(snapshot.lineage.lineage_id, audit.lineage_id, history.lineage_id),
                parent_state_hash=state.state_hash,
            ),
        }
        return ValidatedInitialCycleStateSnapshot(**payload, content_hash=_hash_value(payload))


class BootstrapLeakageValidationPipeline:
    """Small, typed orchestration facade used by BootstrapLeakageGuard."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        logger: Callable[[str, dict[str, object]], None] | None = None,
    ) -> None:
        self._clock = clock
        self._logger = logger
        self._parser = BootstrapLeakageInputParser()
        self._identity = BootstrapIdentityValidator()
        self._temporal = BootstrapTemporalReferenceValidator()
        self._integrity = BootstrapStateIntegrityValidator()
        self._assembler = LeakageValidationReportAssembler()

    def validate(self, **raw_inputs: object) -> ValidatedInitialCycleStateSnapshot:
        inputs = self._parser.parse(**raw_inputs)
        if self._logger:
            self._logger("bootstrap_leakage_validation_started", {"run_id": inputs.snapshot.run_id, "snapshot_id": inputs.snapshot.snapshot_id})
        issues = self._identity.validate(inputs)
        temporal_issues, max_times, trace_count, tool_count = self._temporal.validate(inputs)
        integrity_issues, person_count = self._integrity.validate(inputs)
        issues.extend(temporal_issues)
        issues.extend(integrity_issues)
        if issues:
            if self._logger:
                self._logger("bootstrap_leakage_detected", {"run_id": inputs.snapshot.run_id, "issue_count": len(issues)})
            raise BootstrapLeakageError(issues)
        result = self._assembler.build(
            inputs=inputs,
            max_times=max_times,
            trace_count=trace_count,
            tool_count=tool_count,
            person_count=person_count,
            checked_at=self._clock() if self._clock else inputs.snapshot.state.as_of_time,
        )
        if self._logger:
            self._logger("bootstrap_leakage_validation_completed", {"run_id": inputs.snapshot.run_id, "status": "PASS"})
        return result
