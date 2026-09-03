"""P9.S3.M03 — end-to-end configuration backtest runner."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
import signal
import threading
from time import perf_counter
from typing import Protocol, TypeVar

from .common import ArtifactReference, TerminalStatus, content_sha256, stable_seed
from .execution_models import (
    ExecutionMode,
    PhaseName,
    PhaseRunRequest,
    PhaseRunResult,
    RunnerCapability,
    TrialBacktestRunBundle,
    TrialExecutionLedger,
    TrialExecutionPlan,
    finalize_phase_run_result,
    phase_run_result_sha256,
    trial_bundle_sha256,
)
from quant_pipeline.phase_09.errors import ExecutionTimeoutError, InvariantViolation

from .reason_codes import ReasonCode


T = TypeVar("T")


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class ExecutionController(Protocol):
    def run(self, operation: Callable[[], T], timeout_seconds: float) -> T: ...


class SignalExecutionController:
    """Hard-deadline controller for the main thread on POSIX platforms."""

    def run(self, operation: Callable[[], T], timeout_seconds: float) -> T:
        if timeout_seconds <= 0:
            raise ExecutionTimeoutError("execution deadline already exhausted")
        if (
            threading.current_thread() is not threading.main_thread()
            or not hasattr(signal, "setitimer")
        ):
            raise ExecutionTimeoutError(
                "hard timeout is unavailable outside the POSIX main thread"
            )

        def handler(_signum: int, _frame: object) -> None:
            raise ExecutionTimeoutError("phase execution exceeded its hard deadline")

        previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, handler)
        previous_timer = signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        try:
            return operation()
        finally:
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)
            signal.signal(signal.SIGALRM, previous_handler)


class DirectExecutionController:
    """Explicit non-preemptive controller for environments without hard deadlines."""

    def run(self, operation: Callable[[], T], timeout_seconds: float) -> T:
        if timeout_seconds <= 0:
            raise ExecutionTimeoutError("execution deadline already exhausted")
        return operation()


class PhaseRunner(Protocol):
    @property
    def runner_id(self) -> str: ...

    @property
    def capability(self) -> RunnerCapability: ...

    def run(self, request: PhaseRunRequest) -> PhaseRunResult: ...


class PhaseRunnerRegistry:
    """Explicit registry; no universal module-ID executor."""

    def __init__(self) -> None:
        self._runners: dict[PhaseName, PhaseRunner] = {}

    def register(self, phase: PhaseName, runner: PhaseRunner) -> None:
        if phase in self._runners:
            raise ValueError(f"runner already registered for {phase.value}")
        self._runners[phase] = runner

    def require(self, phase: PhaseName) -> PhaseRunner:
        try:
            return self._runners[phase]
        except KeyError as exc:
            raise KeyError(f"no runner registered for {phase.value}") from exc



def _result_contract_errors(request: PhaseRunRequest, result: PhaseRunResult) -> tuple[str, ...]:
    errors: list[str] = []
    if result.phase is not request.phase:
        errors.append("phase mismatch")
    if phase_run_result_sha256(result) != result.result_sha256:
        errors.append("phase result hash mismatch")
    if result.input_artifacts != request.input_artifacts:
        errors.append("input artifact echo mismatch")
    for artifact in result.output_artifacts:
        if artifact.run_id != request.run_id or artifact.cycle_id != request.cycle_id:
            errors.append(f"artifact run/cycle mismatch: {artifact.artifact_id}")
    if result.phase is PhaseName.P8 and result.p8_handoff is not None:
        handoff = result.p8_handoff
        if (
            handoff.run_id != request.run_id
            or handoff.cycle_id != request.cycle_id
            or handoff.trial_id != request.trial_id
            or handoff.fold_id != request.fold_id
        ):
            errors.append("P8 handoff execution identity mismatch")
    return tuple(errors)


def _terminal_from_phase(result: PhaseRunResult) -> TerminalStatus:
    if result.status in {TerminalStatus.SUCCESS, TerminalStatus.NO_ACTION_VALID}:
        return result.status
    return result.status


def execute_trial_plan(
    plan: TrialExecutionPlan,
    registry: PhaseRunnerRegistry,
    *,
    clock: Clock | None = None,
    execution_controller: ExecutionController | None = None,
    perf_counter_fn: Callable[[], float] = perf_counter,
) -> TrialExecutionLedger:
    """Execute all trials deterministically through public phase-runner protocols."""

    clock = clock or SystemClock()
    if execution_controller is None:
        execution_controller = (
            SignalExecutionController()
            if plan.resource_budget.hard_timeout_supported
            else DirectExecutionController()
        )
    bundles: list[TrialBacktestRunBundle] = []
    terminal_by_trial: dict[str, TerminalStatus] = {}
    successful_upstream = {TerminalStatus.SUCCESS, TerminalStatus.NO_ACTION_VALID}
    reserved_cpu_seconds = 0
    for trial in plan.trials:
        trial_started = clock.now()
        clock_started = perf_counter_fn()
        phase_results: list[PhaseRunResult] = []
        reasons: list[str] = []
        status = TerminalStatus.SUCCESS
        current_artifacts = plan.initial_artifacts

        unsatisfied = [
            dependency
            for dependency in trial.depends_on_trial_ids
            if terminal_by_trial.get(dependency) not in successful_upstream
        ]
        if unsatisfied:
            status = TerminalStatus.CANCELLED_UPSTREAM
            reasons.append("P9_TRIAL_CANCELLED_UPSTREAM")

        requested_cpu_seconds = int(
            trial.cpu_seconds
            or max(1, int(float(plan.resource_budget.maximum_seconds)))
        )
        requested_memory_mb = trial.memory_mb
        if (
            status is not TerminalStatus.CANCELLED_UPSTREAM
            and plan.resource_budget.maximum_memory_mb_per_trial is not None
            and requested_memory_mb is not None
            and requested_memory_mb > plan.resource_budget.maximum_memory_mb_per_trial
        ):
            status = TerminalStatus.RESOURCE_EXHAUSTED
            reasons.extend((
                ReasonCode.TRIAL_RESOURCE_EXHAUSTED.value,
                ReasonCode.TRIAL_MEMORY_LIMIT_EXCEEDED.value,
            ))
        required_labels = set(plan.resource_budget.required_worker_labels)
        if (
            status is not TerminalStatus.CANCELLED_UPSTREAM
            and required_labels
            and not required_labels.issubset(set(trial.worker_labels))
        ):
            status = TerminalStatus.RESOURCE_EXHAUSTED
            reasons.extend((
                ReasonCode.TRIAL_RESOURCE_EXHAUSTED.value,
                ReasonCode.TRIAL_WORKER_LABEL_MISMATCH.value,
            ))
        if (
            status is not TerminalStatus.CANCELLED_UPSTREAM
            and plan.resource_budget.maximum_total_cpu_seconds is not None
            and reserved_cpu_seconds + requested_cpu_seconds
            > plan.resource_budget.maximum_total_cpu_seconds
        ):
            status = TerminalStatus.RESOURCE_EXHAUSTED
            reasons.extend((
                ReasonCode.TRIAL_RESOURCE_EXHAUSTED.value,
                ReasonCode.TOTAL_CPU_BUDGET_EXCEEDED.value,
            ))
        if status not in {
            TerminalStatus.CANCELLED_UPSTREAM,
            TerminalStatus.RESOURCE_EXHAUSTED,
        }:
            reserved_cpu_seconds += requested_cpu_seconds

        if status in {TerminalStatus.CANCELLED_UPSTREAM, TerminalStatus.RESOURCE_EXHAUSTED}:
            pass
        elif trial.mode is ExecutionMode.FIXED_P8_REPLAY:
            if trial.fixed_p8_handoff is None:
                raise InvariantViolation("FIXED_P8_REPLAY trial lacks fixed handoff")
            fixed_handoff = trial.fixed_p8_handoff
            fixed_artifact = ArtifactReference(
                artifact_id=f"fixed-p8:{trial.trial_id}",
                artifact_type="P8_EVALUATION_HANDOFF",
                artifact_schema_name="P8EvaluationHandoff",
                artifact_schema_version=fixed_handoff.schema_version,
                content_sha256=fixed_handoff.replay_sha256,
                producer_module_id="P8.S5.M03",
                run_id=plan.run_id,
                cycle_id=plan.cycle_id,
                available_at=fixed_handoff.valuations[-1].valuation_time,
                location=f"memory://fixed-p8/{trial.trial_id}",
                record_count=1,
            )
            phase_body = {
                "phase": PhaseName.P8,
                "runner_id": "p9.s3.fixed_p8_replay",
                "runner_version": "1.0.0",
                "capability": RunnerCapability.RESEARCH,
                "status": (
                    TerminalStatus.NO_ACTION_VALID
                    if not fixed_handoff.orders
                    else TerminalStatus.SUCCESS
                ),
                "started_at": trial_started,
                "completed_at": clock.now(),
                "input_artifacts": current_artifacts,
                "output_artifacts": (fixed_artifact,),
                "p8_handoff": fixed_handoff,
            }
            result = finalize_phase_run_result(
                PhaseRunResult(**phase_body, result_sha256="0" * 64)
            )
            phase_results.append(result)
            status = result.status
        else:
            for phase in (PhaseName.P5, PhaseName.P6, PhaseName.P7, PhaseName.P8):
                try:
                    runner = registry.require(phase)
                except KeyError:
                    status = TerminalStatus.CAPABILITY_UNAVAILABLE
                    reasons.append(ReasonCode.PHASE_CAPABILITY_UNAVAILABLE.value)
                    break
                if (
                    phase is PhaseName.P8
                    and runner.capability is RunnerCapability.LEGACY_RESEARCH_ONLY
                ):
                    reasons.append(ReasonCode.LEGACY_P8_NOT_QUALIFIABLE.value)
                request = PhaseRunRequest(
                    phase=phase,
                    run_id=plan.run_id,
                    cycle_id=plan.cycle_id,
                    trial_id=trial.trial_id,
                    fold_id=trial.fold_id,
                    configuration_id=trial.configuration_id,
                    configuration_sha256=trial.configuration_sha256,
                    seed=stable_seed(
                        trial.seed_namespace,
                        trial.trial_id,
                        trial.fold_id,
                        phase.value,
                    ),
                    input_artifacts=current_artifacts,
                    resource_budget=plan.resource_budget,
                )
                elapsed_before_phase = perf_counter_fn() - clock_started
                trial_limit = float(trial.cpu_seconds or plan.resource_budget.maximum_seconds)
                remaining = trial_limit - elapsed_before_phase
                try:
                    result = execution_controller.run(lambda: runner.run(request), remaining)
                except ExecutionTimeoutError:
                    status = TerminalStatus.RESOURCE_EXHAUSTED
                    reasons.append(ReasonCode.TRIAL_RESOURCE_EXHAUSTED.value)
                    break
                phase_results.append(result)
                contract_errors = _result_contract_errors(request, result)
                if contract_errors:
                    status = TerminalStatus.INVALID
                    reasons.append(ReasonCode.PHASE_CONTRACT_REJECTED.value)
                    reasons.extend(contract_errors)
                    break
                if result.status not in {TerminalStatus.SUCCESS, TerminalStatus.NO_ACTION_VALID}:
                    status = _terminal_from_phase(result)
                    reasons.extend(result.reason_codes or (ReasonCode.TRIAL_FAILED.value,))
                    break
                current_artifacts = result.output_artifacts
                if result.status is TerminalStatus.NO_ACTION_VALID:
                    status = TerminalStatus.NO_ACTION_VALID

        elapsed = Decimal(str(perf_counter_fn() - clock_started))
        if elapsed > plan.resource_budget.maximum_seconds:
            status = TerminalStatus.RESOURCE_EXHAUSTED
            reasons.append(ReasonCode.TRIAL_RESOURCE_EXHAUSTED.value)
        output_count = sum(len(result.output_artifacts) for result in phase_results)
        if output_count > plan.resource_budget.maximum_output_artifacts:
            status = TerminalStatus.RESOURCE_EXHAUSTED
            reasons.append(ReasonCode.TRIAL_RESOURCE_EXHAUSTED.value)

        trial_completed = clock.now()
        body = {
            "trial_id": trial.trial_id,
            "fold_id": trial.fold_id,
            "configuration_id": trial.configuration_id,
            "configuration_sha256": trial.configuration_sha256,
            "mode": trial.mode,
            "status": status,
            "phase_results": tuple(phase_results),
            "started_at": trial_started,
            "completed_at": trial_completed,
            "resource_seconds": elapsed,
            "reason_codes": tuple(sorted(set(reasons))),
        }
        semantic_body = {
            "trial_id": trial.trial_id,
            "fold_id": trial.fold_id,
            "configuration_id": trial.configuration_id,
            "configuration_sha256": trial.configuration_sha256,
            "mode": trial.mode,
            "status": status,
            "phase_outputs": tuple(
                (
                    result.phase,
                    result.status,
                    result.runner_id,
                    result.runner_version,
                    result.result_sha256,
                    tuple(artifact.content_sha256 for artifact in result.output_artifacts),
                )
                for result in phase_results
            ),
            "reason_codes": tuple(sorted(set(reasons))),
        }
        bundle = TrialBacktestRunBundle(
            **body,
            bundle_sha256="0" * 64,
        )
        computed_bundle_hash = trial_bundle_sha256(bundle)
        if computed_bundle_hash != content_sha256(semantic_body):
            raise InvariantViolation("internal trial hash preimages diverged")
        finalized_bundle = bundle.model_copy(update={"bundle_sha256": computed_bundle_hash})
        bundles.append(finalized_bundle)
        terminal_by_trial[trial.trial_id] = finalized_bundle.status

    counts = Counter(bundle.status for bundle in bundles)
    terminal_counts = tuple(sorted(counts.items(), key=lambda item: item[0].value))
    ledger_body = {
        "plan_id": plan.plan_id,
        "bundle_hashes": tuple(bundle.bundle_sha256 for bundle in bundles),
        "reserved_trial_ids": tuple(trial.trial_id for trial in plan.reserved_trials),
        "source_plan_sha256": plan.source_plan_sha256,
        "source_trial_count": plan.source_trial_count,
        "terminal_counts": terminal_counts,
    }
    return TrialExecutionLedger(
        plan_id=plan.plan_id,
        bundles=tuple(bundles),
        reserved_trial_ids=tuple(trial.trial_id for trial in plan.reserved_trials),
        source_plan_sha256=plan.source_plan_sha256,
        source_trial_count=plan.source_trial_count,
        terminal_counts=terminal_counts,
        content_sha256=content_sha256(ledger_body),
    )
