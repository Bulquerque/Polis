"""Executable Phase 09 cycle state machine.

The runner is deliberately independent from subphase payload internals. Each
subphase executor returns a cryptographically identified checkpoint. The state
machine enforces S1→S10 order, run/cycle conservation, fail-closed propagation,
and deterministic final receipts. Scientific subphase runners are injected via
small adapters rather than hidden behind a universal executor.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from pydantic import Field, model_validator

from quant_pipeline.phase_09.contracts.base import ModuleStatus, NonEmptyStr, Sha256Hex, StrictModel
from quant_pipeline.phase_09.contracts.integrity import payload_sha256
from quant_pipeline.phase_09.errors import ContractError, InvariantViolation

EXPECTED_SUBPHASES = tuple(f"P9.S{index}" for index in range(1, 11))
_BLOCKING_STATUSES = {ModuleStatus.FAILED, ModuleStatus.INVALID}


class CycleTerminalState(StrEnum):
    ROBUST = "ROBUST"
    BACKTEST_OVERFIT_RISK = "BACKTEST_OVERFIT_RISK"
    NO_ACTION_VALID = "NO_ACTION_VALID"
    STRUCTURALLY_FRAGILE = "STRUCTURALLY_FRAGILE"
    LIVE_DEGRADATION = "LIVE_DEGRADATION"
    ATTRIBUTION_TO_CORRECT_PHASE = "ATTRIBUTION_TO_CORRECT_PHASE"
    FEEDBACK_NEXT_CYCLE_ONLY = "FEEDBACK_NEXT_CYCLE_ONLY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INVALID = "INVALID"


class CycleContext(StrictModel):
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    configuration_id: NonEmptyStr
    started_at: datetime

    @model_validator(mode="after")
    def validate_time(self) -> "CycleContext":
        if (
            self.started_at.tzinfo is None
            or self.started_at.utcoffset() != UTC.utcoffset(self.started_at)
        ):
            raise ValueError("cycle started_at must be UTC")
        return self


class SubphaseExecutionOutcome(StrictModel):
    subphase_id: NonEmptyStr
    status: ModuleStatus
    payload_sha256: Sha256Hex
    output_artifact_ids: tuple[NonEmptyStr, ...] = ()
    semantic_state: NonEmptyStr | None = None
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_status(self) -> "SubphaseExecutionOutcome":
        if self.status in _BLOCKING_STATUSES and not self.reason_codes:
            raise ValueError("blocking subphase outcomes require reason codes")
        if self.status is ModuleStatus.SUCCESS and not self.output_artifact_ids:
            raise ValueError("successful subphase outcome requires output artifacts")
        return self


class SubphaseCheckpoint(StrictModel):
    subphase_id: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    configuration_id: NonEmptyStr
    status: ModuleStatus
    payload_sha256: Sha256Hex
    upstream_checkpoint_sha256s: tuple[Sha256Hex, ...]
    output_artifact_ids: tuple[NonEmptyStr, ...] = ()
    semantic_state: NonEmptyStr | None = None
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()
    started_at: datetime
    completed_at: datetime
    checkpoint_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_checkpoint(self) -> "SubphaseCheckpoint":
        if (
            self.started_at.tzinfo is None
            or self.started_at.utcoffset() != UTC.utcoffset(self.started_at)
        ):
            raise ValueError("checkpoint started_at must be UTC")
        if (
            self.completed_at.tzinfo is None
            or self.completed_at.utcoffset() != UTC.utcoffset(self.completed_at)
        ):
            raise ValueError("checkpoint completed_at must be UTC")
        if self.completed_at < self.started_at:
            raise ValueError("checkpoint completed_at precedes started_at")
        expected = payload_sha256(
            self.model_dump(mode="python", exclude={"checkpoint_sha256"})
        )
        if expected != self.checkpoint_sha256:
            raise ValueError("checkpoint hash mismatch")
        return self


class CycleExecutionReceipt(StrictModel):
    context: CycleContext
    expected_subphase_ids: tuple[NonEmptyStr, ...] = EXPECTED_SUBPHASES
    checkpoints: tuple[SubphaseCheckpoint, ...]
    status: ModuleStatus
    terminal_state: CycleTerminalState
    completed_at: datetime
    reason_codes: tuple[NonEmptyStr, ...] = ()
    receipt_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_receipt(self) -> "CycleExecutionReceipt":
        ids = tuple(item.subphase_id for item in self.checkpoints)
        if ids != self.expected_subphase_ids:
            raise ValueError("cycle checkpoints must exactly cover S1-S10 in order")
        if any(
            (item.run_id, item.cycle_id, item.configuration_id)
            != (
                self.context.run_id,
                self.context.cycle_id,
                self.context.configuration_id,
            )
            for item in self.checkpoints
        ):
            raise ValueError("cycle checkpoint identity mismatch")
        if (
            self.completed_at.tzinfo is None
            or self.completed_at.utcoffset() != UTC.utcoffset(self.completed_at)
        ):
            raise ValueError("cycle completed_at must be UTC")
        child_statuses = {item.status for item in self.checkpoints}
        if self.status is ModuleStatus.SUCCESS and child_statuses != {ModuleStatus.SUCCESS}:
            raise ValueError("successful cycle requires all subphases SUCCESS")
        if self.status in _BLOCKING_STATUSES and not self.reason_codes:
            raise ValueError("blocked cycle requires reason codes")
        expected = payload_sha256(
            self.model_dump(mode="python", exclude={"receipt_sha256"})
        )
        if expected != self.receipt_sha256:
            raise ValueError("cycle receipt hash mismatch")
        return self


class SubphaseExecutor(Protocol):
    @property
    def subphase_id(self) -> str: ...

    def execute(
        self,
        context: CycleContext,
        upstream: tuple[SubphaseCheckpoint, ...],
    ) -> SubphaseExecutionOutcome: ...


class CycleClock(Protocol):
    def now(self) -> datetime: ...


class SystemCycleClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class P9CycleRunner:
    """Execute exact S1→S10 order and preserve every terminal state."""

    def __init__(self, *, clock: CycleClock | None = None) -> None:
        self._clock = clock or SystemCycleClock()

    def run(
        self,
        *,
        context: CycleContext,
        executors: tuple[SubphaseExecutor, ...],
        terminal_state: CycleTerminalState,
    ) -> CycleExecutionReceipt:
        executor_ids = tuple(executor.subphase_id for executor in executors)
        if executor_ids != EXPECTED_SUBPHASES:
            raise ContractError("cycle executors must exactly cover S1-S10 in order")

        checkpoints: list[SubphaseCheckpoint] = []
        upstream_blocked = False
        blocking_reasons: set[str] = set()
        for executor in executors:
            started_at = self._clock.now()
            if upstream_blocked:
                outcome = SubphaseExecutionOutcome(
                    subphase_id=executor.subphase_id,
                    status=ModuleStatus.SKIPPED_UPSTREAM_BLOCKED,
                    payload_sha256="0" * 64,
                    reason_codes=("P9_CYCLE_UPSTREAM_BLOCKED",),
                )
            else:
                outcome = executor.execute(context, tuple(checkpoints))
                if outcome.subphase_id != executor.subphase_id:
                    raise InvariantViolation("executor returned a different subphase ID")
            completed_at = self._clock.now()
            values = {
                "subphase_id": outcome.subphase_id,
                "run_id": context.run_id,
                "cycle_id": context.cycle_id,
                "configuration_id": context.configuration_id,
                "status": outcome.status,
                "payload_sha256": outcome.payload_sha256,
                "upstream_checkpoint_sha256s": tuple(
                    item.checkpoint_sha256 for item in checkpoints
                ),
                "output_artifact_ids": outcome.output_artifact_ids,
                "semantic_state": outcome.semantic_state,
                "reason_codes": outcome.reason_codes,
                "limitations": outcome.limitations,
                "started_at": started_at,
                "completed_at": completed_at,
            }
            checkpoint = SubphaseCheckpoint(
                **values,
                checkpoint_sha256=payload_sha256(values),
            )
            checkpoints.append(checkpoint)
            if outcome.status in _BLOCKING_STATUSES:
                upstream_blocked = True
                blocking_reasons.update(outcome.reason_codes)

        statuses = {item.status for item in checkpoints}
        if ModuleStatus.FAILED in statuses:
            cycle_status = ModuleStatus.FAILED
        elif ModuleStatus.INVALID in statuses:
            cycle_status = ModuleStatus.INVALID
        elif statuses == {ModuleStatus.SUCCESS}:
            cycle_status = ModuleStatus.SUCCESS
        else:
            cycle_status = ModuleStatus.LIMITED

        completed_at = self._clock.now()
        reason_codes = tuple(sorted(blocking_reasons))
        values = {
            "context": context,
            "expected_subphase_ids": EXPECTED_SUBPHASES,
            "checkpoints": tuple(checkpoints),
            "status": cycle_status,
            "terminal_state": terminal_state,
            "completed_at": completed_at,
            "reason_codes": reason_codes,
        }
        return CycleExecutionReceipt(
            **values,
            receipt_sha256=payload_sha256(values),
        )
