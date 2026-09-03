from __future__ import annotations

from datetime import datetime

from .errors import S19HashMismatchError, S19PopulationMismatchError, S19TemporalError
from .hashing import deterministic_id, deterministic_seed, hash_without_field, sha256_hex
from .models import (
    ActivationPanel,
    ActivationReason,
    CognitiveCycleSchedule,
    CoverageReason,
    CoverageRecord,
    CurrentPersonStatePanelInput,
    ExecutionStatus,
    HeartbeatConfig,
    ScheduleMetrics,
    ScheduleStep,
    TriggerType,
    ValidatedPopulationManifestInput,
)


def _period(value: datetime) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _verify_hashes(
    activation_panel: ActivationPanel,
    state_panel: CurrentPersonStatePanelInput,
    population: ValidatedPopulationManifestInput,
    config: HeartbeatConfig,
) -> None:
    if not config.verify_input_content_hashes:
        return
    for name, value in [
        ("activation_panel", activation_panel),
        ("current_person_state_panel", state_panel),
        ("validated_population_manifest", population),
    ]:
        if hash_without_field(value) != value.content_hash:
            raise S19HashMismatchError(f"{name} content_hash mismatch")


def _validate_alignment(
    activation_panel: ActivationPanel,
    state_panel: CurrentPersonStatePanelInput,
    population: ValidatedPopulationManifestInput,
) -> None:
    if activation_panel.population_id != population.population_id:
        raise S19PopulationMismatchError("activation and population IDs differ")
    if state_panel.population_id != population.population_id:
        raise S19PopulationMismatchError("state and population IDs differ")
    if activation_panel.as_of != state_panel.as_of:
        raise S19TemporalError("activation and state panels must share as_of")
    population_ids = {item.person_id for item in population.people}
    state_ids = {item.person_id for item in state_panel.records}
    if population_ids != state_ids:
        raise S19PopulationMismatchError("state and population person sets differ")
    activation_people = {item.person_id for item in activation_panel.records}
    if not activation_people <= population_ids:
        raise S19PopulationMismatchError("activation references unknown people")


def _event_step(activation, as_of: datetime, source_lineage_ids: set[str]) -> ScheduleStep:
    tie_hash = sha256_hex(["event", activation.tie_break_hash, activation.activation_id])
    return ScheduleStep(
        schedule_step_id=deterministic_id("schedule-step:event", activation.activation_id),
        sequence_index=0,
        person_id=activation.person_id,
        trigger_type=TriggerType.STIMULUS,
        activation_reason=ActivationReason.STIMULUS_THRESHOLD_MET,
        activation_id=activation.activation_id,
        stimulus_id=activation.stimulus_id,
        heartbeat_period=None,
        priority=activation.stimulus_priority,
        activation_score=activation.activation_score,
        scheduled_at=as_of,
        seed=activation.seed,
        tie_break_hash=tie_hash,
        source_lineage_ids=tuple(sorted(source_lineage_ids)),
    )


def _heartbeat_step(
    person_id: str,
    period: str,
    as_of: datetime,
    config: HeartbeatConfig,
    source_lineage_ids: set[str],
) -> ScheduleStep:
    tie_hash = sha256_hex([config.heartbeat_seed_namespace, period, person_id])
    return ScheduleStep(
        schedule_step_id=deterministic_id("schedule-step:heartbeat", period, person_id),
        sequence_index=0,
        person_id=person_id,
        trigger_type=TriggerType.HEARTBEAT,
        activation_reason=ActivationReason.MONTHLY_HEARTBEAT,
        activation_id=None,
        stimulus_id=None,
        heartbeat_period=period,
        priority=config.heartbeat_priority,
        activation_score=None,
        scheduled_at=as_of,
        seed=deterministic_seed(config.heartbeat_seed_namespace, period, person_id),
        tie_break_hash=tie_hash,
        source_lineage_ids=tuple(sorted(source_lineage_ids)),
    )


def _schedule_sort_key(step: ScheduleStep) -> tuple:
    trigger_rank = 0 if step.trigger_type is TriggerType.STIMULUS else 1
    score = step.activation_score if step.activation_score is not None else -1.0
    return (
        trigger_rank,
        -step.priority,
        -score,
        step.tie_break_hash,
        step.person_id,
        step.schedule_step_id,
    )


def build_cognitive_cycle_schedule(
    activation_panel: ActivationPanel,
    state_panel: CurrentPersonStatePanelInput,
    population: ValidatedPopulationManifestInput,
    config: HeartbeatConfig,
) -> CognitiveCycleSchedule:
    """Combine event activations with deterministic monthly heartbeat coverage."""

    _verify_hashes(activation_panel, state_panel, population, config)
    _validate_alignment(activation_panel, state_panel, population)
    current_period = _period(activation_panel.as_of)
    state_by_person = {item.person_id: item for item in state_panel.records}
    event_by_person: dict[str, list] = {}
    for activation in activation_panel.records:
        event_by_person.setdefault(activation.person_id, []).append(activation)

    steps: list[ScheduleStep] = []
    coverage: list[CoverageRecord] = []
    prior_covered = 0
    disabled = 0
    heartbeat_count = 0
    for member in sorted(population.people, key=lambda item: item.person_id):
        state = state_by_person[member.person_id]
        is_enabled = member.enabled and state.is_active
        if not is_enabled:
            disabled += 1
            coverage.append(
                CoverageRecord(
                    person_id=member.person_id,
                    period=current_period,
                    covered=True,
                    reason=CoverageReason.PERSON_DISABLED,
                    last_cognitive_cycle_at=state.last_cognitive_cycle_at,
                    schedule_step_id=None,
                )
            )
            continue
        person_events = sorted(
            event_by_person.get(member.person_id, []),
            key=lambda item: (
                -item.stimulus_priority,
                -item.activation_score,
                item.tie_break_hash,
                item.activation_id,
            ),
        )
        if person_events:
            created_steps = [
                _event_step(
                    item,
                    activation_panel.as_of,
                    {
                        activation_panel.lineage_id,
                        population.lineage_id,
                        state.lineage_id,
                    },
                )
                for item in person_events
            ]
            steps.extend(created_steps)
            coverage.append(
                CoverageRecord(
                    person_id=member.person_id,
                    period=current_period,
                    covered=True,
                    reason=CoverageReason.EVENT_ACTIVATION,
                    last_cognitive_cycle_at=state.last_cognitive_cycle_at,
                    schedule_step_id=created_steps[0].schedule_step_id,
                )
            )
            continue
        if (
            state.last_cognitive_cycle_at is not None
            and _period(state.last_cognitive_cycle_at) == current_period
        ):
            prior_covered += 1
            coverage.append(
                CoverageRecord(
                    person_id=member.person_id,
                    period=current_period,
                    covered=True,
                    reason=CoverageReason.PRIOR_CYCLE_IN_MONTH,
                    last_cognitive_cycle_at=state.last_cognitive_cycle_at,
                    schedule_step_id=None,
                )
            )
            continue
        heartbeat = _heartbeat_step(
            member.person_id,
            current_period,
            activation_panel.as_of,
            config,
            {
                activation_panel.lineage_id,
                population.lineage_id,
                state.lineage_id,
            },
        )
        heartbeat_count += 1
        steps.append(heartbeat)
        coverage.append(
            CoverageRecord(
                person_id=member.person_id,
                period=current_period,
                covered=True,
                reason=CoverageReason.HEARTBEAT_SCHEDULED,
                last_cognitive_cycle_at=state.last_cognitive_cycle_at,
                schedule_step_id=heartbeat.schedule_step_id,
            )
        )

    ordered = sorted(steps, key=_schedule_sort_key)
    ordered = [
        step.model_copy(update={"sequence_index": index})
        for index, step in enumerate(ordered)
    ]
    coverage = sorted(coverage, key=lambda item: item.person_id)
    status = ExecutionStatus.READY if ordered else ExecutionStatus.READY_EMPTY
    payload = {
        "schema_version": "cognitive_cycle_schedule.v2",
        "contract_version": "p3.s19.v1",
        "schedule_policy": config.schedule_policy,
        "run_id": activation_panel.run_id,
        "cycle_id": activation_panel.cycle_id,
        "target_cycle_id": activation_panel.target_cycle_id,
        "population_id": population.population_id,
        "as_of": activation_panel.as_of,
        "coverage_period": current_period,
        "steps": tuple(ordered),
        "coverage": tuple(coverage),
        "source_lineage_ids": tuple(
            sorted(
                {
                    activation_panel.lineage_id,
                    state_panel.lineage_id,
                    population.lineage_id,
                }
            )
        ),
        "lineage_id": deterministic_id(
            "lineage:p3.s19.m02",
            activation_panel.lineage_id,
            state_panel.lineage_id,
            population.lineage_id,
            config.config_version,
        ),
        "status": status,
        "warnings": (),
        "metrics": ScheduleMetrics(
            population_count=len(population.people),
            enabled_population_count=len(population.people) - disabled,
            event_step_count=len(activation_panel.records),
            heartbeat_step_count=heartbeat_count,
            prior_month_covered_count=prior_covered,
            disabled_count=disabled,
            total_step_count=len(ordered),
            warning_count=0,
        ),
    }
    payload["content_hash"] = sha256_hex(payload)
    return CognitiveCycleSchedule.model_validate(payload)
