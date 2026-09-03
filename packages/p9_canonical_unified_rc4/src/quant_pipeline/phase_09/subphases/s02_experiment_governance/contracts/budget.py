from __future__ import annotations

from decimal import Decimal

from pydantic import Field, model_validator

from quant_pipeline.phase_09.contracts.base import FiniteDecimal

from .base import (
    BudgetState,
    CapabilityState,
    MetricId,
    NonEmptyStr,
    ReasonCode,
    SearchStrategy,
    Sha256Hex,
    StrictModel,
)
from .experiment import ValidatedExperimentSpecification
from .search_space import CompiledSearchSpace


class ResourceCapacitySnapshot(StrictModel):
    snapshot_id: NonEmptyStr
    snapshot_sha256: Sha256Hex
    max_parallel_trials: int = Field(ge=1)
    max_total_cpu_seconds: int = Field(ge=1)
    max_wall_clock_seconds: int = Field(ge=1)
    max_memory_mb_per_trial: int = Field(ge=128)
    available_worker_labels: tuple[NonEmptyStr, ...] = ("cpu",)


class FidelityLevel(StrictModel):
    fidelity_id: NonEmptyStr
    ordinal: int = Field(ge=0)
    resource_fraction: FiniteDecimal
    preserves_transaction_costs: bool
    preserves_lifecycle: bool
    preserves_temporal_order: bool

    @model_validator(mode="after")
    def validate_fraction(self) -> "FidelityLevel":
        if self.resource_fraction <= Decimal("0") or self.resource_fraction > Decimal("1"):
            raise ValueError("resource_fraction must be in (0, 1]")
        return self


class EarlyStoppingPolicy(StrictModel):
    enabled: bool
    signal_metric_ids: tuple[MetricId, ...] = ()
    minimum_completed_cells: int = Field(default=1, ge=1)
    development_only: bool = True

    @model_validator(mode="after")
    def validate_policy(self) -> "EarlyStoppingPolicy":
        if self.enabled and not self.signal_metric_ids:
            raise ValueError("enabled early stopping requires signal metrics")
        if not self.enabled and self.signal_metric_ids:
            raise ValueError("disabled early stopping cannot define signal metrics")
        if self.enabled and not self.development_only:
            raise ValueError("early stopping signals must be development-only")
        return self


class SearchBudgetPolicy(StrictModel):
    policy_id: NonEmptyStr
    policy_sha256: Sha256Hex
    maximum_configurations: int = Field(ge=1)
    maximum_trial_executions: int = Field(ge=1)
    maximum_parallel_trials: int = Field(ge=1)
    maximum_total_cpu_seconds: int = Field(ge=1)
    estimated_cpu_seconds_per_cell: int = Field(ge=1)
    estimated_memory_mb_per_trial: int = Field(ge=128)
    exploration_fraction: FiniteDecimal = Decimal("0.6")
    confirmation_fraction: FiniteDecimal = Decimal("0.25")
    robustness_fraction: FiniteDecimal = Decimal("0.15")
    allow_resource_limited_plan: bool = True

    @model_validator(mode="after")
    def validate_fractions(self) -> "SearchBudgetPolicy":
        fractions = (
            self.exploration_fraction,
            self.confirmation_fraction,
            self.robustness_fraction,
        )
        if any(value < 0 or value > 1 for value in fractions):
            raise ValueError("budget fractions must be in [0,1]")
        if sum(fractions, Decimal("0")) != Decimal("1"):
            raise ValueError("budget fractions must sum to 1")
        return self


class BudgetAllocation(StrictModel):
    stage: NonEmptyStr
    configuration_slots: int = Field(ge=0)
    trial_execution_slots: int = Field(ge=0)
    cpu_seconds_reserved: int = Field(ge=0)


class ComplexityPenaltyPolicy(StrictModel):
    policy_id: NonEmptyStr
    effective_dimension_count: int = Field(ge=0)
    nominal_configuration_count: int | None = Field(default=None, ge=0)
    adaptive_search_depth: int = Field(ge=0)
    penalty_metadata_sha256: Sha256Hex


class SearchBudgetPlan(StrictModel):
    plan_id: NonEmptyStr
    experiment_id: NonEmptyStr
    state: BudgetState
    search_strategy: SearchStrategy
    configuration_limit: int = Field(ge=0)
    trial_execution_limit: int = Field(ge=0)
    parallel_trial_limit: int = Field(ge=0)
    seed_count: int = Field(ge=1)
    evaluation_cell_count: int = Field(ge=1)
    cpu_seconds_per_full_cell: int = Field(ge=1)
    memory_mb_per_trial: int = Field(ge=128)
    wall_clock_seconds_limit: int = Field(ge=1)
    fidelity_levels: tuple[FidelityLevel, ...]
    allocations: tuple[BudgetAllocation, ...]
    early_stopping: EarlyStoppingPolicy
    complexity_penalty: ComplexityPenaltyPolicy
    plan_sha256: Sha256Hex
    reason_codes: tuple[ReasonCode, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_plan(self) -> "SearchBudgetPlan":
        if not self.fidelity_levels:
            raise ValueError("budget plan requires at least one fidelity level")
        ordinals = [level.ordinal for level in self.fidelity_levels]
        if ordinals != sorted(set(ordinals)):
            raise ValueError("fidelity ordinals must be unique and sorted")
        if self.state in {
            BudgetState.BUDGET_INFEASIBLE,
            BudgetState.RESOURCE_CAPABILITY_UNAVAILABLE,
        } and not self.reason_codes:
            raise ValueError("blocking budget state requires reason codes")
        return self


class BudgetReservationReceipt(StrictModel):
    reservation_id: NonEmptyStr
    plan_id: NonEmptyStr
    capacity_snapshot_id: NonEmptyStr
    reserved_cpu_seconds: int = Field(ge=0)
    reserved_parallel_trials: int = Field(ge=0)
    reservation_sha256: Sha256Hex


class BudgetPlanningInput(StrictModel):
    validated_specification: ValidatedExperimentSpecification
    compiled_search_space: CompiledSearchSpace
    resource_capacity: ResourceCapacitySnapshot
    budget_policy: SearchBudgetPolicy
    fidelity_levels: tuple[FidelityLevel, ...]
    early_stopping: EarlyStoppingPolicy


class BudgetPlanningReport(StrictModel):
    state: BudgetState
    reason_codes: tuple[ReasonCode, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_report(self) -> "BudgetPlanningReport":
        if self.state in {
            BudgetState.BUDGET_INFEASIBLE,
            BudgetState.RESOURCE_CAPABILITY_UNAVAILABLE,
        } and not self.reason_codes:
            raise ValueError("blocking budget report requires reason codes")
        return self


class BudgetPlanningOutcome(StrictModel):
    budget_plan: SearchBudgetPlan | None
    reservation_receipt: BudgetReservationReceipt | None
    report: BudgetPlanningReport
