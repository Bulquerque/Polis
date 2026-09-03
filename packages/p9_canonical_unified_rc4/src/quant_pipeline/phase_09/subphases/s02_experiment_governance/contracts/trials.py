from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from quant_pipeline.phase_09.contracts.base import ModuleStatus
from quant_pipeline.phase_09.contracts.integrity import (
    IntegrityEnvelope,
    payload_sha256,
    verify_integrity,
)
from quant_pipeline.phase_09.contracts.receipts import (
    ModuleExecutionReceipt,
    SubphaseExecutionReceipt,
)
from quant_pipeline.phase_09.contracts.s1 import S1ExecutionOutputs

from .base import (
    ConfigurationId,
    NonEmptyStr,
    ReasonCode,
    Sha256Hex,
    StrictModel,
    TrialId,
    TrialPlanState,
    TrialState,
)
from .budget import SearchBudgetPlan
from .configuration import ConfigurationCatalog, SeedPolicyReference
from .experiment import TemporalEvaluationRequest, ValidatedExperimentSpecification
from .parameters import HyperparameterSchemaSnapshot
from .search_space import CompiledSearchSpace


class WorkerCapabilitySnapshot(StrictModel):
    snapshot_id: NonEmptyStr
    snapshot_sha256: Sha256Hex
    worker_labels: tuple[NonEmptyStr, ...]
    max_parallel_trials: int = Field(ge=1)
    max_memory_mb_per_trial: int = Field(ge=128)


class SchedulerPolicy(StrictModel):
    policy_id: NonEmptyStr
    policy_sha256: Sha256Hex
    retry_limit: int = Field(ge=0, le=10)
    retryable_terminal_states: tuple[TrialState, ...]
    checkpoint_every_completed_trials: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_retry_states(self) -> "SchedulerPolicy":
        prohibited = {TrialState.COMPLETED, TrialState.INVALID, TrialState.INFEASIBLE}
        if prohibited & set(self.retryable_terminal_states):
            raise ValueError("completed/invalid/infeasible trials cannot be retried")
        return self


class TrialResourceRequest(StrictModel):
    cpu_seconds: int = Field(ge=1)
    memory_mb: int = Field(ge=128)
    worker_labels: tuple[NonEmptyStr, ...] = ("cpu",)


class TrialExecutionSlot(StrictModel):
    trial_id: TrialId
    configuration_id: ConfigurationId | None
    stage: NonEmptyStr
    evaluation_cell_id: NonEmptyStr
    seed: int = Field(ge=0)
    fidelity_id: NonEmptyStr
    bracket_id: NonEmptyStr | None = None
    rung: int = Field(default=0, ge=0)
    depends_on_trial_ids: tuple[TrialId, ...] = ()
    resource_request: TrialResourceRequest
    initial_state: TrialState = TrialState.PLANNED
    allowed_terminal_states: tuple[TrialState, ...]
    idempotency_key: Sha256Hex
    adaptive_assignment_key: NonEmptyStr | None = None
    selection_rank: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_slot(self) -> "TrialExecutionSlot":
        if self.trial_id in self.depends_on_trial_ids:
            raise ValueError("trial cannot depend on itself")
        if len(self.depends_on_trial_ids) != len(set(self.depends_on_trial_ids)):
            raise ValueError("trial dependencies must be unique")
        if TrialState.COMPLETED not in self.allowed_terminal_states:
            raise ValueError("allowed terminal states must include COMPLETED")
        if self.initial_state not in {TrialState.PLANNED, TrialState.RESERVED}:
            raise ValueError("trial initial state must be PLANNED or RESERVED")
        if self.configuration_id is None:
            if self.initial_state is not TrialState.RESERVED:
                raise ValueError("unassigned trial must start RESERVED")
            if self.adaptive_assignment_key is None or self.selection_rank is None:
                raise ValueError("unassigned trial requires adaptive assignment metadata")
        else:
            if self.initial_state is not TrialState.PLANNED:
                raise ValueError("assigned trial must start PLANNED")
            if self.adaptive_assignment_key is not None or self.selection_rank is not None:
                raise ValueError("assigned trial cannot contain adaptive assignment metadata")
        return self


class TrialExecutionPlan(StrictModel):
    plan_id: NonEmptyStr
    experiment_id: NonEmptyStr
    state: TrialPlanState
    temporal_evaluation_request: TemporalEvaluationRequest
    slots: tuple[TrialExecutionSlot, ...]
    plan_sha256: Sha256Hex
    reason_codes: tuple[ReasonCode, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_plan(self) -> "TrialExecutionPlan":
        ids = [slot.trial_id for slot in self.slots]
        if len(ids) != len(set(ids)):
            raise ValueError("trial IDs must be unique")
        known = set(ids)
        for slot in self.slots:
            if not set(slot.depends_on_trial_ids) <= known:
                raise ValueError("trial dependency references unknown trial")
        if self.state in {
            TrialPlanState.NO_TRIALS_VALID,
            TrialPlanState.SCHEDULER_INFEASIBLE,
            TrialPlanState.BUNDLE_INVALID,
        } and not self.reason_codes:
            raise ValueError("blocking trial plan state requires reason codes")
        return self


class TrialStateTemplateRecord(StrictModel):
    trial_id: TrialId
    current_state: TrialState
    attempt: int = Field(default=0, ge=0)
    assigned_worker_id: NonEmptyStr | None = None
    result_artifact_id: NonEmptyStr | None = None
    reason_codes: tuple[ReasonCode, ...] = ()


class TrialStateLedgerTemplate(StrictModel):
    ledger_id: NonEmptyStr
    plan_id: NonEmptyStr
    records: tuple[TrialStateTemplateRecord, ...]
    terminal_states: tuple[TrialState, ...]
    ledger_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_ledger(self) -> "TrialStateLedgerTemplate":
        ids = [record.trial_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("trial state records must be unique")
        required = {
            TrialState.COMPLETED,
            TrialState.INVALID,
            TrialState.INFEASIBLE,
            TrialState.EARLY_STOPPED,
            TrialState.RESOURCE_EXHAUSTED,
            TrialState.FAILED,
            TrialState.QUARANTINED,
            TrialState.CANCELLED_UPSTREAM,
        }
        if not required <= set(self.terminal_states):
            raise ValueError("trial state ledger omits required terminal states")
        return self


class TrialSchedulingInput(StrictModel):
    validated_specification: ValidatedExperimentSpecification
    configuration_catalog: ConfigurationCatalog
    budget_plan: SearchBudgetPlan
    compiled_search_space: CompiledSearchSpace
    scheduler_policy: SchedulerPolicy
    worker_capabilities: WorkerCapabilitySnapshot
    seed_policy: SeedPolicyReference


class S2ExecutionOutputs(StrictModel):
    validated_specification: ValidatedExperimentSpecification | None
    parameter_snapshot: HyperparameterSchemaSnapshot | None
    compiled_search_space: CompiledSearchSpace | None
    budget_plan: SearchBudgetPlan | None
    configuration_catalog: ConfigurationCatalog | None
    trial_plan: TrialExecutionPlan | None
    trial_state_ledger: TrialStateLedgerTemplate | None
    module_receipts: tuple[ModuleExecutionReceipt, ...]
    subphase_receipt: SubphaseExecutionReceipt
    limitations: tuple[NonEmptyStr, ...] = ()


class FoundationExperimentBundlePayload(StrictModel):
    contract_name: Literal["P9_FOUNDATION_EXPERIMENT_BUNDLE_V1"] = (
        "P9_FOUNDATION_EXPERIMENT_BUNDLE_V1"
    )
    contract_version: Literal["1.0.0"] = "1.0.0"
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    s1_outputs_sha256: Sha256Hex
    s2_outputs_sha256: Sha256Hex
    s1_outputs: S1ExecutionOutputs
    s2_outputs: S2ExecutionOutputs
    input_bundle_sha256: Sha256Hex
    limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_bundle(self) -> "FoundationExperimentBundlePayload":
        if self.s1_outputs.subphase_receipt.payload.status is not ModuleStatus.SUCCESS:
            raise ValueError("S1-S2 bundle requires successful S1")
        if self.s2_outputs.subphase_receipt.payload.status not in {
            ModuleStatus.SUCCESS,
            ModuleStatus.LIMITED,
        }:
            raise ValueError("S1-S2 bundle requires successful or limited S2")
        if self.s2_outputs.trial_plan is None:
            raise ValueError("S1-S2 bundle requires trial plan")
        return self


class FoundationExperimentBundle(StrictModel):
    payload: FoundationExperimentBundlePayload
    integrity: IntegrityEnvelope

    @model_validator(mode="after")
    def validate_integrity(self) -> "FoundationExperimentBundle":
        if not verify_integrity(self.payload, self.integrity):
            raise ValueError("S1-S2 bundle integrity mismatch")
        if self.payload.s1_outputs_sha256 != payload_sha256(self.payload.s1_outputs):
            raise ValueError("s1_outputs_sha256 mismatch")
        if self.payload.s2_outputs_sha256 != payload_sha256(self.payload.s2_outputs):
            raise ValueError("s2_outputs_sha256 mismatch")
        return self


class TrialSchedulingReport(StrictModel):
    state: TrialPlanState
    reason_codes: tuple[ReasonCode, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_report(self) -> "TrialSchedulingReport":
        if self.state in {
            TrialPlanState.NO_TRIALS_VALID,
            TrialPlanState.SCHEDULER_INFEASIBLE,
            TrialPlanState.BUNDLE_INVALID,
        } and not self.reason_codes:
            raise ValueError("blocking scheduling report requires reason codes")
        return self


class TrialSchedulingOutcome(StrictModel):
    trial_plan: TrialExecutionPlan | None
    trial_state_ledger: TrialStateLedgerTemplate | None
    report: TrialSchedulingReport


class FoundationExecutionResult(StrictModel):
    s2_outputs: S2ExecutionOutputs
    foundation_bundle: FoundationExperimentBundle | None
