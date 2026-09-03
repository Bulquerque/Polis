"""Typed contracts for end-to-end trial execution."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from .common import (
    ArtifactReference,
    DiagnosticRecord,
    EvidenceRecord,
    FiniteDecimal,
    ModuleId,
    NonEmptyStr,
    SemVer,
    Sha256,
    StrictModel,
    TerminalStatus,
    UtcDateTime,
)
from .integrity_models import P8EvaluationHandoff


class PhaseName(StrEnum):
    P5 = "P5"
    P6 = "P6"
    P7 = "P7"
    P8 = "P8"


class ExecutionMode(StrEnum):
    FULL_PIPELINE = "FULL_PIPELINE"
    FIXED_P8_REPLAY = "FIXED_P8_REPLAY"


class RunnerCapability(StrEnum):
    PRODUCTION = "PRODUCTION"
    RESEARCH = "RESEARCH"
    LEGACY_RESEARCH_ONLY = "LEGACY_RESEARCH_ONLY"
    UNAVAILABLE = "UNAVAILABLE"


class ResourceBudget(StrictModel):
    maximum_seconds: FiniteDecimal = Field(gt=Decimal("0"))
    maximum_output_artifacts: int = Field(default=128, ge=1)
    hard_timeout_supported: bool = False
    maximum_total_cpu_seconds: int | None = Field(default=None, ge=1)
    maximum_memory_mb_per_trial: int | None = Field(default=None, ge=128)
    required_worker_labels: tuple[NonEmptyStr, ...] = ()


class TrialSpec(StrictModel):
    trial_id: NonEmptyStr
    configuration_id: NonEmptyStr
    configuration_sha256: Sha256
    fold_id: NonEmptyStr
    seed_namespace: NonEmptyStr
    mode: ExecutionMode = ExecutionMode.FULL_PIPELINE
    fixed_p8_handoff: P8EvaluationHandoff | None = None
    stage: NonEmptyStr = "FULL"
    fidelity_id: NonEmptyStr = "FULL"
    bracket_id: NonEmptyStr | None = None
    rung: int = Field(default=0, ge=0)
    depends_on_trial_ids: tuple[NonEmptyStr, ...] = ()
    cpu_seconds: int | None = Field(default=None, ge=1)
    memory_mb: int | None = Field(default=None, ge=128)
    worker_labels: tuple[NonEmptyStr, ...] = ()
    allowed_terminal_states: tuple[NonEmptyStr, ...] = ()
    idempotency_key: Sha256 | None = None
    source_initial_state: NonEmptyStr = "PLANNED"

    @model_validator(mode="after")
    def validate_mode(self) -> Self:
        if self.mode is ExecutionMode.FIXED_P8_REPLAY and self.fixed_p8_handoff is None:
            raise ValueError("FIXED_P8_REPLAY requires fixed_p8_handoff")
        if self.mode is ExecutionMode.FULL_PIPELINE and self.fixed_p8_handoff is not None:
            raise ValueError("FULL_PIPELINE cannot include fixed_p8_handoff")
        if self.trial_id in self.depends_on_trial_ids:
            raise ValueError("trial cannot depend on itself")
        if len(set(self.depends_on_trial_ids)) != len(self.depends_on_trial_ids):
            raise ValueError("trial dependencies must be unique")
        return self


class ReservedTrialSpec(StrictModel):
    trial_id: NonEmptyStr
    fold_id: NonEmptyStr
    stage: NonEmptyStr
    seed_namespace: NonEmptyStr
    fidelity_id: NonEmptyStr
    bracket_id: NonEmptyStr | None = None
    rung: int = Field(default=0, ge=0)
    depends_on_trial_ids: tuple[NonEmptyStr, ...] = ()
    cpu_seconds: int = Field(ge=1)
    memory_mb: int = Field(ge=128)
    worker_labels: tuple[NonEmptyStr, ...]
    allowed_terminal_states: tuple[NonEmptyStr, ...]
    idempotency_key: Sha256
    adaptive_assignment_key: NonEmptyStr
    selection_rank: int = Field(ge=0)


class TrialExecutionPlan(StrictModel):
    plan_id: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    contract_pack_version: SemVer
    trials: tuple[TrialSpec, ...]
    reserved_trials: tuple[ReservedTrialSpec, ...] = ()
    source_plan_sha256: Sha256 | None = None
    source_plan_state: NonEmptyStr | None = None
    source_trial_count: int | None = Field(default=None, ge=1)
    initial_artifacts: tuple[ArtifactReference, ...] = ()
    resource_budget: ResourceBudget

    @model_validator(mode="after")
    def validate_trials(self) -> Self:
        executable_ids = [trial.trial_id for trial in self.trials]
        reserved_ids = [trial.trial_id for trial in self.reserved_trials]
        all_ids = executable_ids + reserved_ids
        if not all_ids:
            raise ValueError("trial plan cannot be empty")
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("trial IDs must be unique across executable and reserved slots")
        known = set(all_ids)
        for trial in (*self.trials, *self.reserved_trials):
            if not set(trial.depends_on_trial_ids) <= known:
                raise ValueError("trial dependency references unknown trial")
        if self.source_trial_count is not None and self.source_trial_count != len(all_ids):
            raise ValueError("source_trial_count must equal executable plus reserved trials")
        # Require executable trials to be topologically ordered. This makes the
        # deterministic runner dependency-safe without inventing a scheduler.
        seen: set[str] = set()
        for trial in self.trials:
            if not set(trial.depends_on_trial_ids) <= seen:
                raise ValueError(
                    "executable trials must be topologically ordered and cannot "
                    "depend on reserved slots"
                )
            seen.add(trial.trial_id)
        return self


class PhaseRunRequest(StrictModel):
    phase: PhaseName
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    trial_id: NonEmptyStr
    fold_id: NonEmptyStr
    configuration_id: NonEmptyStr
    configuration_sha256: Sha256
    seed: int = Field(ge=0)
    input_artifacts: tuple[ArtifactReference, ...]
    resource_budget: ResourceBudget


class PhaseRunResult(StrictModel):
    phase: PhaseName
    runner_id: NonEmptyStr
    runner_version: SemVer
    capability: RunnerCapability
    status: TerminalStatus
    started_at: UtcDateTime
    completed_at: UtcDateTime
    input_artifacts: tuple[ArtifactReference, ...]
    output_artifacts: tuple[ArtifactReference, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    diagnostics: tuple[DiagnosticRecord, ...] = ()
    reason_codes: tuple[NonEmptyStr, ...] = ()
    p8_handoff: P8EvaluationHandoff | None = None
    result_sha256: Sha256

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        if self.phase is PhaseName.P8 and self.status in {
            TerminalStatus.SUCCESS,
            TerminalStatus.NO_ACTION_VALID,
        } and self.p8_handoff is None:
            raise ValueError("successful P8 result requires typed p8_handoff")
        if self.phase is not PhaseName.P8 and self.p8_handoff is not None:
            raise ValueError("only P8 may publish p8_handoff")
        if self.status is TerminalStatus.SUCCESS and not self.output_artifacts:
            raise ValueError("SUCCESS phase result requires output artifacts")
        return self


class TrialBacktestRunBundle(StrictModel):
    trial_id: NonEmptyStr
    fold_id: NonEmptyStr
    configuration_id: NonEmptyStr
    configuration_sha256: Sha256
    mode: ExecutionMode
    status: TerminalStatus
    phase_results: tuple[PhaseRunResult, ...]
    started_at: UtcDateTime
    completed_at: UtcDateTime
    resource_seconds: FiniteDecimal
    reason_codes: tuple[NonEmptyStr, ...] = ()
    bundle_sha256: Sha256

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        phase_names = [result.phase for result in self.phase_results]
        if len(phase_names) != len(set(phase_names)):
            raise ValueError("phase results must be unique")
        if self.mode is ExecutionMode.FULL_PIPELINE:
            expected = [PhaseName.P5, PhaseName.P6, PhaseName.P7, PhaseName.P8]
            if phase_names != expected[: len(phase_names)]:
                raise ValueError("FULL_PIPELINE phase results must be a canonical P5→P8 prefix")
            successful = {TerminalStatus.SUCCESS, TerminalStatus.NO_ACTION_VALID}
            if self.status in successful and phase_names != expected:
                raise ValueError("successful FULL_PIPELINE bundle requires P5,P6,P7,P8")
        if self.mode is ExecutionMode.FIXED_P8_REPLAY and phase_names != [PhaseName.P8]:
            raise ValueError("FIXED_P8_REPLAY must contain only P8")
        return self


class TrialExecutionLedger(StrictModel):
    plan_id: NonEmptyStr
    bundles: tuple[TrialBacktestRunBundle, ...]
    reserved_trial_ids: tuple[NonEmptyStr, ...] = ()
    source_plan_sha256: Sha256 | None = None
    source_trial_count: int | None = Field(default=None, ge=1)
    terminal_counts: tuple[tuple[TerminalStatus, int], ...]
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_conservation(self) -> Self:
        bundle_ids = [bundle.trial_id for bundle in self.bundles]
        if len(bundle_ids) != len(set(bundle_ids)):
            raise ValueError("trial ledger contains duplicate bundles")
        if set(bundle_ids) & set(self.reserved_trial_ids):
            raise ValueError("reserved trials cannot also have execution bundles")
        if self.source_trial_count is not None and self.source_trial_count != (
            len(bundle_ids) + len(self.reserved_trial_ids)
        ):
            raise ValueError("trial ledger does not conserve source trial slots")
        return self


def phase_run_result_sha256(result: PhaseRunResult) -> str:
    """Recompute the canonical producer payload hash for a phase result."""

    from .common import content_sha256

    return content_sha256(result.model_dump(mode="python", exclude={"result_sha256"}))


def finalize_phase_run_result(result: PhaseRunResult) -> PhaseRunResult:
    """Return a copy carrying the canonical non-self-referential result hash."""

    return result.model_copy(update={"result_sha256": phase_run_result_sha256(result)})


def trial_bundle_sha256(bundle: TrialBacktestRunBundle) -> str:
    """Recompute the stable semantic hash, excluding operational timestamps."""

    from .common import content_sha256

    preimage = {
        "trial_id": bundle.trial_id,
        "fold_id": bundle.fold_id,
        "configuration_id": bundle.configuration_id,
        "configuration_sha256": bundle.configuration_sha256,
        "mode": bundle.mode,
        "status": bundle.status,
        "phase_outputs": tuple(
            (
                result.phase,
                result.status,
                result.runner_id,
                result.runner_version,
                result.result_sha256,
                tuple(artifact.content_sha256 for artifact in result.output_artifacts),
            )
            for result in bundle.phase_results
        ),
        "reason_codes": bundle.reason_codes,
    }
    return content_sha256(preimage)


def trial_ledger_sha256(ledger: TrialExecutionLedger) -> str:
    """Recompute the ledger hash from ordered bundle identities and counts."""

    from .common import content_sha256

    return content_sha256(
        {
            "plan_id": ledger.plan_id,
            "bundle_hashes": tuple(bundle.bundle_sha256 for bundle in ledger.bundles),
            "reserved_trial_ids": ledger.reserved_trial_ids,
            "source_plan_sha256": ledger.source_plan_sha256,
            "source_trial_count": ledger.source_trial_count,
            "terminal_counts": ledger.terminal_counts,
        }
    )
