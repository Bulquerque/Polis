from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from .errors import (
    S18DuplicateConflictError,
    S18HashMismatchError,
    S18InputError,
    S18TemporalViolationError,
)
from .forbidden import reject_forbidden_fields
from .hashing import deterministic_id, hash_without_field, sha256_hex
from .models import (
    EndogenousStimulusRecord,
    EndogenousStimulusStream,
    ExecutionStatus,
    Phase3RunSnapshot,
    PriorCycleEndogenousStimulusQueue,
    QueueAdmissionDecision,
    QueueConsumptionRecord,
    QueueDecisionReason,
    QueueLoaderMetrics,
    StimulusBusConfig,
)

REQUIRED_INPUTS = (
    "prior_cycle_endogenous_stimulus_queue",
    "phase3_run_snapshot",
    "stimulus_event_bus_config",
)


def load_endogenous_stimulus_queue(inputs: Mapping[str, Any]) -> EndogenousStimulusStream:
    """Load the prior-cycle queue while enforcing the N→N+1 boundary."""

    reject_forbidden_fields(inputs)
    _require_inputs(inputs)
    try:
        queue = PriorCycleEndogenousStimulusQueue.model_validate(
            inputs["prior_cycle_endogenous_stimulus_queue"]
        )
        snapshot = Phase3RunSnapshot.model_validate(inputs["phase3_run_snapshot"])
        config = StimulusBusConfig.model_validate(inputs["stimulus_event_bus_config"])
    except ValidationError as exc:
        raise S18InputError(f"P3.S18.M01 input validation failed: {exc}") from exc

    _validate_queue_envelope(queue, snapshot, config)

    accepted: dict[str, EndogenousStimulusRecord] = {}
    decisions: list[QueueAdmissionDecision] = []
    consumption_ledger: list[QueueConsumptionRecord] = []
    warnings: list[str] = []
    expired_count = 0
    duplicate_count = 0

    for item in sorted(queue.items, key=_queue_sort_key):
        _validate_item_temporality(item, queue, snapshot)
        if item.expires_at < snapshot.as_of:
            expired_count += 1
            decisions.append(
                QueueAdmissionDecision(
                    stimulus_id=item.stimulus_id,
                    reason=QueueDecisionReason.EXPIRED,
                    detail="expires_at is before current as_of",
                )
            )
            consumption_ledger.append(
                _consumption_record(
                    queue=queue,
                    snapshot=snapshot,
                    item=item,
                    decision=QueueDecisionReason.EXPIRED,
                )
            )
            continue

        existing = accepted.get(item.stimulus_id)
        if existing is not None:
            if sha256_hex(existing) != sha256_hex(item):
                raise S18DuplicateConflictError(
                    f"conflicting records share stimulus_id={item.stimulus_id}"
                )
            duplicate_count += 1
            decisions.append(
                QueueAdmissionDecision(
                    stimulus_id=item.stimulus_id,
                    reason=QueueDecisionReason.DUPLICATE_COLLAPSED,
                    detail="exact duplicate in prior-cycle queue",
                )
            )
            consumption_ledger.append(
                _consumption_record(
                    queue=queue,
                    snapshot=snapshot,
                    item=item,
                    decision=QueueDecisionReason.DUPLICATE_COLLAPSED,
                )
            )
            continue

        accepted[item.stimulus_id] = item
        decisions.append(
            QueueAdmissionDecision(
                stimulus_id=item.stimulus_id,
                reason=QueueDecisionReason.ACCEPTED,
                detail="prior-cycle endogenous stimulus admitted",
            )
        )
        consumption_ledger.append(
            _consumption_record(
                queue=queue,
                snapshot=snapshot,
                item=item,
                decision=QueueDecisionReason.ACCEPTED,
            )
        )

    items = tuple(sorted(accepted.values(), key=_queue_sort_key))
    if expired_count:
        warnings.append(f"expired_items_dropped:{expired_count}")
    if duplicate_count:
        warnings.append(f"exact_duplicates_collapsed:{duplicate_count}")

    if not queue.items:
        status = ExecutionStatus.READY_EMPTY
    elif expired_count or duplicate_count:
        status = ExecutionStatus.DEGRADED
    elif items:
        status = ExecutionStatus.READY
    else:
        status = ExecutionStatus.DEGRADED

    payload: dict[str, Any] = {
        "schema_version": "endogenous_stimulus_stream.v2",
        "contract_version": "p3.s18.v1",
        "run_id": snapshot.run_id,
        "cycle_id": snapshot.cycle_id,
        "target_cycle_id": snapshot.target_cycle_id,
        "as_of": snapshot.as_of,
        "items": items,
        "admission_decisions": tuple(decisions),
        "consumption_ledger": tuple(
            sorted(consumption_ledger, key=lambda record: record.consumption_id)
        ),
        "lineage_id": deterministic_id(
            "lineage:p3.s18.m01",
            queue.lineage_id,
            snapshot.lineage_id,
            config.config_version,
        ),
        "status": status,
        "warnings": tuple(warnings),
        "metrics": QueueLoaderMetrics(
            input_record_count=len(queue.items),
            output_record_count=len(items),
            expired_count=expired_count,
            duplicate_collapsed_count=duplicate_count,
            warning_count=len(warnings),
        ),
    }
    payload["content_hash"] = sha256_hex(payload)
    return EndogenousStimulusStream.model_validate(payload)


def _require_inputs(inputs: Mapping[str, Any]) -> None:
    missing = [name for name in REQUIRED_INPUTS if name not in inputs]
    unexpected = sorted(set(inputs) - set(REQUIRED_INPUTS))
    if missing or unexpected:
        raise S18InputError(f"missing={missing}; unexpected={unexpected}")


def _validate_queue_envelope(
    queue: PriorCycleEndogenousStimulusQueue,
    snapshot: Phase3RunSnapshot,
    config: StimulusBusConfig,
) -> None:
    if queue.source_run_id != snapshot.run_id:
        raise S18InputError("queue source_run_id does not match current run_id")
    if queue.target_cycle_id not in {snapshot.cycle_id, snapshot.target_cycle_id}:
        raise S18TemporalViolationError("queue target_cycle_id is not the current cycle")
    if queue.source_cycle_id in {snapshot.cycle_id, snapshot.target_cycle_id}:
        raise S18TemporalViolationError("same-cycle endogenous queue is forbidden")
    if queue.created_at > snapshot.as_of:
        raise S18TemporalViolationError("queue created_at is after current as_of")
    if config.allow_same_cycle_endogenous:
        raise S18InputError("S18 v1 forbids enabling same-cycle endogenous stimuli")
    if config.verify_input_content_hashes:
        actual = hash_without_field(queue)
        if actual != queue.content_hash:
            raise S18HashMismatchError(
                f"queue content_hash mismatch: expected={queue.content_hash} actual={actual}"
            )


def _validate_item_temporality(
    item: EndogenousStimulusRecord,
    queue: PriorCycleEndogenousStimulusQueue,
    snapshot: Phase3RunSnapshot,
) -> None:
    if item.created_cycle_id != queue.source_cycle_id:
        raise S18TemporalViolationError(
            f"item {item.stimulus_id} created_cycle_id differs from queue source_cycle_id"
        )
    if item.created_cycle_id in {snapshot.cycle_id, snapshot.target_cycle_id}:
        raise S18TemporalViolationError(
            f"item {item.stimulus_id} creates a same-cycle back-edge"
        )
    if item.target_cycle_id not in {snapshot.cycle_id, snapshot.target_cycle_id}:
        raise S18TemporalViolationError(
            f"item {item.stimulus_id} targets a different cycle"
        )
    if item.available_at > snapshot.as_of:
        raise S18TemporalViolationError(
            f"item {item.stimulus_id} is not available at current as_of"
        )


def _queue_sort_key(item: EndogenousStimulusRecord) -> tuple[object, ...]:
    return (-item.priority, -item.salience, item.available_at, item.stimulus_id)


def _consumption_record(
    *,
    queue: PriorCycleEndogenousStimulusQueue,
    snapshot: Phase3RunSnapshot,
    item: EndogenousStimulusRecord,
    decision: QueueDecisionReason,
) -> QueueConsumptionRecord:
    return QueueConsumptionRecord(
        queue_id=queue.queue_id,
        stimulus_id=item.stimulus_id,
        produced_in_cycle=item.created_cycle_id,
        available_from_cycle=item.target_cycle_id,
        consumed_in_cycle=snapshot.cycle_id,
        consumer_run_id=snapshot.run_id,
        decision=decision,
        consumption_id=deterministic_id(
            "queue-consumption",
            queue.queue_id,
            item.stimulus_id,
            snapshot.run_id,
            snapshot.cycle_id,
            decision.value,
        ),
    )
