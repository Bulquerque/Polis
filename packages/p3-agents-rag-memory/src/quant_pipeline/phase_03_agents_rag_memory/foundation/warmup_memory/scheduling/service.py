from __future__ import annotations

import calendar
import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from .errors import SchedulingIssue, WarmupCheckpointPlanError, WarmupScheduleBuildError
from .models import (
    ActivationConfigView,
    ArtifactStatus,
    CheckpointPlanLineage,
    CheckpointReason,
    EventReference,
    HeartbeatConfig,
    PlannedCheckpoint,
    ScheduleItemKind,
    ScheduleLineage,
    ScheduleSummary,
    ValidatedInitialSocialGraphView,
    ValidatedPopulationManifestView,
    ValidatedWarmupHistoryView,
    WarmupCheckpointConfig,
    WarmupCheckpointPlan,
    WarmupEventSchedule,
    WarmupMode,
    WarmupScheduleItem,
)

EventSink = Callable[[str, Mapping[str, object]], None]
FORBIDDEN_FIELDS = {
    "future_return", "candidate_score", "rank_score", "portfolio_weight",
    "trade_decision", "buy_sell_signal",
}


def _emit(sink: EventSink | None, event: str, **dimensions: object) -> None:
    if sink is not None:
        sink(event, dimensions)


def _json_ready(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list)):
        return [_json_ready(item) for item in value]
    return value


def _hash(value: object) -> str:
    payload = json.dumps(_json_ready(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _scan_forbidden(value: object, path: str = "root") -> list[SchedulingIssue]:
    issues: list[SchedulingIssue] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}.{key}"
            if str(key) in FORBIDDEN_FIELDS:
                issues.append(SchedulingIssue("P3_S10_FORBIDDEN_FIELD", f"Forbidden field: {key}", child))
            issues.extend(_scan_forbidden(item, child))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            issues.extend(_scan_forbidden(item, f"{path}[{index}]"))
    return issues


def _validation_issues(exc: ValidationError, prefix: str) -> list[SchedulingIssue]:
    return [
        SchedulingIssue(
            code=f"{prefix}_INPUT_INVALID",
            message=error["msg"],
            path=".".join(str(item) for item in error["loc"]),
            details={"type": error["type"]},
        )
        for error in exc.errors(include_url=False, include_input=False)
    ]


def _month_pairs(start: datetime, end: datetime) -> tuple[tuple[int, int], ...]:
    year, month = start.year, start.month
    pairs: list[tuple[int, int]] = []
    while (year, month) <= (end.year, end.month):
        pairs.append((year, month))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return tuple(pairs)


def _month_end(year: int, month: int, config: HeartbeatConfig) -> datetime:
    last_day = calendar.monthrange(year, month)[1]
    return datetime(
        year, month, last_day,
        config.due_hour_utc, config.due_minute_utc, config.due_second_utc,
        tzinfo=UTC,
    )


def _schedule_item_id(payload: Mapping[str, object]) -> str:
    return f"s10-item-{_hash(payload)[:20]}"


def build_warmup_schedule(
    *,
    validated_warmup_history: Mapping[str, Any],
    validated_population_manifest: Mapping[str, Any],
    validated_initial_social_graph: Mapping[str, Any],
    activation_config: Mapping[str, Any],
    heartbeat_config: Mapping[str, Any],
    event_sink: EventSink | None = None,
) -> WarmupEventSchedule:
    started = perf_counter()
    run_id = str(validated_warmup_history.get("run_id", "unknown"))
    _emit(event_sink, "module_started", run_id=run_id, module_id="P3.S10.M01")
    try:
        forbidden = _scan_forbidden({
            "validated_warmup_history": validated_warmup_history,
            "validated_population_manifest": validated_population_manifest,
            "validated_initial_social_graph": validated_initial_social_graph,
            "activation_config": activation_config,
            "heartbeat_config": heartbeat_config,
        })
        if forbidden:
            raise WarmupScheduleBuildError(forbidden)
        try:
            history = ValidatedWarmupHistoryView.model_validate(validated_warmup_history)
            population = ValidatedPopulationManifestView.model_validate(validated_population_manifest)
            graph = ValidatedInitialSocialGraphView.model_validate(validated_initial_social_graph)
            activation = ActivationConfigView.model_validate(activation_config)
            heartbeat = HeartbeatConfig.model_validate(heartbeat_config)
        except ValidationError as exc:
            raise WarmupScheduleBuildError(_validation_issues(exc, "P3_S10_M01")) from exc

        issues: list[SchedulingIssue] = []
        if population.run_id != history.run_id or graph.run_id != history.run_id:
            issues.append(SchedulingIssue("P3_S10_M01_RUN_ID_MISMATCH", "All inputs must share run_id"))
        if population.snapshot_id != history.snapshot_id or graph.snapshot_id != history.snapshot_id:
            issues.append(SchedulingIssue("P3_S10_M01_SNAPSHOT_ID_MISMATCH", "All inputs must share snapshot_id"))
        if graph.population_hash != population.population_hash:
            issues.append(SchedulingIssue("P3_S10_M01_POPULATION_HASH_MISMATCH", "Graph must bind to population hash"))
        if activation.monthly_heartbeat is not heartbeat.enabled:
            issues.append(SchedulingIssue("P3_S10_M01_HEARTBEAT_CONFIG_CONFLICT", "Activation and heartbeat configs conflict"))
        person_ids = {person.person_id for person in population.persons}
        for index, edge in enumerate(graph.records):
            if edge.source_person_id not in person_ids or edge.target_person_id not in person_ids:
                issues.append(SchedulingIssue(
                    "P3_S10_M01_GRAPH_ORPHAN_PERSON", "Social edge references unknown person", f"graph.records[{index}]"
                ))
        if issues:
            raise WarmupScheduleBuildError(issues)
        _emit(event_sink, "input_contract_validated", run_id=history.run_id, module_id="P3.S10.M01")

        raw: list[dict[str, object]] = []
        month_count = 0
        if history.mode is WarmupMode.HISTORICAL_REPLAY:
            if history.warmup_start is None or history.warmup_end is None:
                raise WarmupScheduleBuildError([
                    SchedulingIssue("P3_S10_M01_WARMUP_BOUNDS_MISSING", "Historical replay requires warmup_start and warmup_end")
                ])
            for record in history.records:
                payload = {
                    "kind": ScheduleItemKind.EVENT_RELEASE.value,
                    "logical_time": record.available_at,
                    "priority": activation.event_priority,
                }
                identity_payload = {
                    **payload,
                    "event_id": record.event_id,
                    "history_record_id": record.history_record_id,
                    "history_hash": history.history_hash,
                }
                raw.append({
                    **payload,
                    "schedule_item_id": _schedule_item_id(identity_payload),
                    "deduplication_key": f"event:{record.event_id}:{record.available_at.isoformat()}",
                    "event_ref": EventReference(
                        history_record_id=record.history_record_id,
                        event_id=record.event_id,
                        source_id=record.source_id,
                        payload_ref=record.payload_ref,
                        underlyings=record.underlyings,
                        propositions=record.propositions,
                    ),
                    "person_id": None,
                    "heartbeat_period": None,
                    "source_lineage_ids": (record.lineage.lineage_id,),
                })
            months = _month_pairs(history.warmup_start, history.warmup_end)
            month_count = len(months)
            for year, month in months:
                due = _month_end(year, month, heartbeat)
                if due > history.warmup_end:
                    if not heartbeat.include_partial_months:
                        continue
                    due = history.warmup_end
                if due < history.warmup_start:
                    continue
                if due >= history.evaluation_start:
                    due = history.evaluation_start - timedelta(microseconds=1)
                period = f"{year:04d}-{month:02d}"
                for person_id in sorted(person_ids):
                    payload = {
                        "kind": ScheduleItemKind.HEARTBEAT_OBLIGATION.value,
                        "logical_time": due,
                        "priority": activation.heartbeat_priority,
                        "person_id": person_id,
                        "heartbeat_period": period,
                    }
                    identity_payload = {**payload, "population_hash": population.population_hash}
                    raw.append({
                        **payload,
                        "schedule_item_id": _schedule_item_id(identity_payload),
                        "deduplication_key": f"heartbeat:{person_id}:{period}",
                        "event_ref": None,
                        "source_lineage_ids": (population.lineage_id, graph.lineage_id),
                    })

        raw.sort(key=lambda item: (
            item["logical_time"], item["priority"], item.get("person_id") or "",
            getattr(item.get("event_ref"), "event_id", ""), item["schedule_item_id"],
        ))
        dedup = [str(item["deduplication_key"]) for item in raw]
        if len(dedup) != len(set(dedup)):
            raise WarmupScheduleBuildError([
                SchedulingIssue("P3_S10_M01_DUPLICATE_SCHEDULE_ITEM", "Schedule contains duplicate deduplication keys")
            ])
        items = tuple(
            WarmupScheduleItem(sequence_number=index, **item)
            for index, item in enumerate(raw, start=1)
        )
        activation_hash = _hash(activation)
        heartbeat_hash = _hash(heartbeat)
        schedule_payload = {
            "run_id": history.run_id,
            "snapshot_id": history.snapshot_id,
            "mode": history.mode.value,
            "history_hash": history.history_hash,
            "population_hash": population.population_hash,
            "graph_hash": graph.graph_hash,
            "activation_config_hash": activation_hash,
            "heartbeat_config_hash": heartbeat_hash,
            "items": items,
        }
        schedule_hash = _hash(schedule_payload)
        output = WarmupEventSchedule(
            artifact_id=f"p3-s10-schedule-{history.run_id}-{schedule_hash[:16]}",
            run_id=history.run_id,
            snapshot_id=history.snapshot_id,
            as_of=history.as_of,
            evaluation_start=history.evaluation_start,
            mode=history.mode,
            status=ArtifactStatus.READY,
            schedule_start=items[0].logical_time if items else None,
            schedule_end=items[-1].logical_time if items else None,
            items=items,
            schedule_hash=schedule_hash,
            activation_config_hash=activation_hash,
            heartbeat_config_hash=heartbeat_hash,
            lineage=ScheduleLineage(
                lineage_id=f"s10-schedule-lineage-{schedule_hash[:16]}",
                history_artifact_id=history.artifact_id,
                history_hash=history.history_hash,
                population_artifact_id=population.artifact_id,
                population_hash=population.population_hash,
                social_graph_artifact_id=graph.artifact_id,
                graph_hash=graph.graph_hash,
                source_lineage_ids=tuple(sorted({
                    str(history.lineage.get("lineage_id", "s9-lineage")),
                    population.lineage_id,
                    graph.lineage_id,
                })),
            ),
            summary=ScheduleSummary(
                event_item_count=sum(item.kind is ScheduleItemKind.EVENT_RELEASE for item in items),
                heartbeat_item_count=sum(item.kind is ScheduleItemKind.HEARTBEAT_OBLIGATION for item in items),
                person_count=len(person_ids),
                month_count=month_count,
                total_item_count=len(items),
            ),
        )
        _emit(
            event_sink, "module_succeeded", run_id=history.run_id, module_id="P3.S10.M01",
            duration_ms=round((perf_counter()-started)*1000, 3), output_record_count=len(items),
        )
        return output
    except WarmupScheduleBuildError as exc:
        _emit(
            event_sink, "module_failed", run_id=run_id, module_id="P3.S10.M01",
            duration_ms=round((perf_counter()-started)*1000, 3), error_count=len(exc.issues),
        )
        raise


def build_warmup_checkpoint_plan(
    *,
    warmup_event_schedule: Mapping[str, Any],
    warmup_checkpoint_config: Mapping[str, Any],
    event_sink: EventSink | None = None,
) -> WarmupCheckpointPlan:
    started = perf_counter()
    run_id = str(warmup_event_schedule.get("run_id", "unknown"))
    _emit(event_sink, "module_started", run_id=run_id, module_id="P3.S10.M02")
    try:
        forbidden = _scan_forbidden({
            "warmup_event_schedule": warmup_event_schedule,
            "warmup_checkpoint_config": warmup_checkpoint_config,
        })
        if forbidden:
            raise WarmupCheckpointPlanError(forbidden)
        try:
            schedule = WarmupEventSchedule.model_validate(warmup_event_schedule)
            config = WarmupCheckpointConfig.model_validate(warmup_checkpoint_config)
        except ValidationError as exc:
            raise WarmupCheckpointPlanError(_validation_issues(exc, "P3_S10_M02")) from exc
        _emit(event_sink, "input_contract_validated", run_id=schedule.run_id, module_id="P3.S10.M02")

        descriptors: list[dict[str, object]] = []
        final_boundary = schedule.evaluation_start - timedelta(microseconds=1)
        if schedule.mode is WarmupMode.GENESIS_ONLY:
            descriptors.append({
                "after_schedule_sequence_number": 0,
                "logical_time": final_boundary,
                "reason": CheckpointReason.GENESIS,
                "final": True,
            })
        else:
            by_month: dict[tuple[int, int], WarmupScheduleItem] = {}
            for item in schedule.items:
                by_month[(item.logical_time.year, item.logical_time.month)] = item
            for item in by_month.values():
                descriptors.append({
                    "after_schedule_sequence_number": item.sequence_number,
                    "logical_time": item.logical_time,
                    "reason": CheckpointReason.MONTHLY_BOUNDARY,
                    "final": False,
                })
            descriptors.sort(key=lambda row: (row["logical_time"], row["after_schedule_sequence_number"]))
            final_after = schedule.items[-1].sequence_number if schedule.items else 0
            final_time = max(schedule.schedule_end or final_boundary, schedule.items[-1].logical_time if schedule.items else final_boundary)
            if final_time >= schedule.evaluation_start:
                raise WarmupCheckpointPlanError([
                    SchedulingIssue("P3_S10_M02_FINAL_NOT_BEFORE_EVALUATION", "Final checkpoint must be before evaluation")
                ])
            if descriptors and descriptors[-1]["after_schedule_sequence_number"] == final_after and descriptors[-1]["logical_time"] == final_time:
                descriptors[-1]["final"] = True
            else:
                descriptors.append({
                    "after_schedule_sequence_number": final_after,
                    "logical_time": final_time,
                    "reason": CheckpointReason.FINAL_REPLAY_BOUNDARY,
                    "final": True,
                })
        if len(descriptors) > config.max_checkpoint_count:
            raise WarmupCheckpointPlanError([
                SchedulingIssue("P3_S10_M02_CHECKPOINT_LIMIT_EXCEEDED", "Checkpoint count exceeds configured cap")
            ])

        checkpoints: list[PlannedCheckpoint] = []
        previous: str | None = None
        for index, descriptor in enumerate(descriptors, start=1):
            identity = {
                "schedule_hash": schedule.schedule_hash,
                "index": index,
                "after": descriptor["after_schedule_sequence_number"],
                "logical_time": descriptor["logical_time"],
                "reason": descriptor["reason"].value,
                "families": config.required_state_families,
            }
            checkpoint_id = f"s10-checkpoint-{_hash(identity)[:20]}"
            checkpoint = PlannedCheckpoint(
                checkpoint_id=checkpoint_id,
                sequence_number=index,
                after_schedule_sequence_number=descriptor["after_schedule_sequence_number"],
                logical_time=descriptor["logical_time"],
                reason=descriptor["reason"],
                previous_checkpoint_id=previous,
                required_state_families=config.required_state_families,
                final=descriptor["final"],
            )
            checkpoints.append(checkpoint)
            previous = checkpoint_id
        config_hash = _hash(config)
        plan_payload = {
            "run_id": schedule.run_id,
            "snapshot_id": schedule.snapshot_id,
            "schedule_hash": schedule.schedule_hash,
            "config_hash": config_hash,
            "checkpoints": checkpoints,
        }
        plan_hash = _hash(plan_payload)
        final = next(checkpoint for checkpoint in checkpoints if checkpoint.final)
        output = WarmupCheckpointPlan(
            artifact_id=f"p3-s10-checkpoint-plan-{schedule.run_id}-{plan_hash[:16]}",
            run_id=schedule.run_id,
            snapshot_id=schedule.snapshot_id,
            as_of=schedule.as_of,
            evaluation_start=schedule.evaluation_start,
            mode=schedule.mode,
            status=ArtifactStatus.READY,
            schedule_hash=schedule.schedule_hash,
            checkpoint_config_hash=config_hash,
            checkpoints=tuple(checkpoints),
            final_checkpoint_id=final.checkpoint_id,
            final_checkpoint_time=final.logical_time,
            resume_supported=config.resume_supported,
            plan_hash=plan_hash,
            lineage=CheckpointPlanLineage(
                lineage_id=f"s10-checkpoint-lineage-{plan_hash[:16]}",
                schedule_artifact_id=schedule.artifact_id,
                schedule_hash=schedule.schedule_hash,
                checkpoint_config_hash=config_hash,
                source_lineage_ids=(schedule.lineage.lineage_id,),
            ),
        )
        _emit(
            event_sink, "module_succeeded", run_id=schedule.run_id, module_id="P3.S10.M02",
            duration_ms=round((perf_counter()-started)*1000, 3), output_record_count=len(checkpoints),
        )
        return output
    except WarmupCheckpointPlanError as exc:
        _emit(
            event_sink, "module_failed", run_id=run_id, module_id="P3.S10.M02",
            duration_ms=round((perf_counter()-started)*1000, 3), error_count=len(exc.issues),
        )
        raise
