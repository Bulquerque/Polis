"""Wave 2 mutation, target-payoff, solver, and robust-evaluation models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from ..foundation.artifacts import FrozenModel
from ..foundation.hashing import utc
from .enums import (
    CalculationStatus,
    CapabilityStatus,
    MutationOperator,
    ObjectiveFamily,
    SolverMethod,
    SolverStatus,
    TargetPayoffMode,
)
from .strategy_models import StrategyLeg


class MutationOperatorDefinition(FrozenModel):
    operator: MutationOperator
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...]
    risk_effect: str
    complexity_cost: int = Field(ge=0)
    allowed_templates: tuple[str, ...] = ()
    maximum_applications: int = Field(ge=1)


class MutationApplication(FrozenModel):
    mutation_id: str
    parent_candidate_id: str
    child_candidate_id: str
    operator: MutationOperator
    parameters: dict[str, str] = Field(default_factory=dict)
    application_index: int = Field(ge=1)
    valid: bool
    reason_code: str | None = None


class MarketImpliedState(FrozenModel):
    market_implied_state_id: str
    underlying_id: str
    decision_time: datetime
    state_grid: tuple[Decimal, ...]
    risk_neutral_probabilities: tuple[Decimal, ...]
    method: str
    smoothing: str
    repair_status: CalculationStatus
    strike_coverage: Decimal = Field(ge=0, le=1)
    tail_extrapolation_status: CalculationStatus
    source_contract_ids: tuple[str, ...]
    source_expiration: datetime | None = None
    source_currency: str | None = None
    source_multiplier: Decimal | None = Field(default=None, gt=0)
    source_exercise_style: str | None = None
    risk_free_rate: Decimal | None = None
    dividend_yield: Decimal | None = None
    status: CalculationStatus
    reason_code: str | None = None

    @field_validator("decision_time", "source_expiration")
    @classmethod
    def normalize_time(cls, value: datetime | None) -> datetime | None:
        return None if value is None else utc(value)

    @model_validator(mode="after")
    def validate_mass(self) -> "MarketImpliedState":
        if self.status is CalculationStatus.AVAILABLE:
            if not self.state_grid or len(self.state_grid) != len(self.risk_neutral_probabilities):
                raise ValueError("available market-implied state requires aligned grid and probabilities")
            mass = sum(self.risk_neutral_probabilities, Decimal("0"))
            if abs(mass - Decimal("1")) > Decimal("0.0000001"):
                raise ValueError("risk-neutral probability mass must sum to one")
        return self


class TargetPayoffRecord(FrozenModel):
    target_payoff_id: str
    underlying_id: str
    decision_time: datetime
    horizon_days: int = Field(gt=0)
    objective_family: ObjectiveFamily
    mode: TargetPayoffMode
    terminal_state_grid: tuple[Decimal, ...]
    raw_target_payoff: tuple[Decimal, ...]
    regularized_target_payoff: tuple[Decimal, ...]
    scenario_probabilities: tuple[Decimal, ...]
    cost_budget: Decimal | None = Field(default=None, ge=0)
    risk_budget: Decimal | None = Field(default=None, ge=0)
    complexity_budget: int = Field(ge=1)
    belief_state_id: str
    ambiguity_set_id: str | None = None
    market_implied_state_id: str | None = None
    confidence: Decimal = Field(ge=0, le=1)
    status: CalculationStatus
    reason_code: str | None = None

    @field_validator("decision_time")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc(value)

    @model_validator(mode="after")
    def validate_vectors(self) -> "TargetPayoffRecord":
        lengths = {
            len(self.terminal_state_grid),
            len(self.raw_target_payoff),
            len(self.regularized_target_payoff),
            len(self.scenario_probabilities),
        }
        if len(lengths) != 1:
            raise ValueError("target payoff vectors must be aligned")
        return self


class TargetPayoffRegularizationReport(FrozenModel):
    target_payoff_id: str
    raw_range: Decimal
    regularized_range: Decimal
    clipping_count: int = Field(ge=0)
    smoothing_strength: Decimal = Field(ge=0, le=1)
    confidence_shrinkage: Decimal = Field(ge=0, le=1)
    finite: bool


class TargetPayoffQualification(FrozenModel):
    target_payoff_id: str
    qualified: bool
    reason_codes: tuple[str, ...]
    finite: bool
    bounded: bool
    confidence_sufficient: bool
    cost_budget_available: bool
    risk_budget_available: bool


class ReplicationBasisInstrument(FrozenModel):
    basis_id: str
    target_payoff_id: str
    underlying_id: str
    instrument_id: str
    leg: StrategyLeg
    payoff_vector: tuple[Decimal, ...]
    entry_cost: Decimal
    liquidity: Decimal | None
    margin_proxy: Decimal | None
    quantity_lower_bound: int
    quantity_upper_bound: int
    status: CalculationStatus


class StrategySynthesisProblem(FrozenModel):
    problem_id: str
    target_payoff_id: str
    underlying_id: str
    state_grid: tuple[Decimal, ...]
    target_vector: tuple[Decimal, ...]
    scenario_weights: tuple[Decimal, ...]
    basis_ids: tuple[str, ...]
    max_legs: int = Field(ge=1)
    max_quantity: int = Field(ge=1)
    cost_budget: Decimal | None = Field(default=None, ge=0)
    risk_budget: Decimal | None = Field(default=None, ge=0)


class SolverQuantity(FrozenModel):
    basis_id: str
    quantity: Decimal


class SolverResult(FrozenModel):
    solver_result_id: str
    problem_id: str
    target_payoff_id: str
    method: SolverMethod
    solver_name: str
    solver_version: str
    status: SolverStatus
    quantities: tuple[SolverQuantity, ...]
    objective_value: Decimal | None
    best_bound: Decimal | None
    optimality_gap: Decimal | None
    runtime_ms: int = Field(ge=0)
    iterations: int = Field(ge=0)
    node_count: int = Field(ge=0)
    timeout: bool
    seed: int
    diagnostics: tuple[str, ...] = ()


class PathwiseValuationRecord(FrozenModel):
    candidate_id: str
    scenario_id: str
    marks: tuple[Decimal, ...]
    maximum_path_loss: Decimal | None
    method: str
    status: CalculationStatus
    reason_code: str | None = None


class RobustAmbiguityEvaluation(FrozenModel):
    candidate_id: str
    status: CapabilityStatus
    nominal_expected_payoff: Decimal | None
    worst_case_expected_payoff: Decimal | None
    worst_case_expected_utility: Decimal | None
    worst_case_cvar: Decimal | None
    ambiguity_regret: Decimal | None
    distribution_sensitivity: Decimal | None
    ambiguity_set_id: str | None
    reason_code: str | None = None


class ArchiveCoverageReport(FrozenModel):
    archive_mode: str
    niches_defined: int = Field(ge=0)
    niches_filled: int = Field(ge=0)
    coverage: Decimal = Field(ge=0, le=1)
    candidate_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    empty_regions: tuple[str, ...]
    generation_saturated: bool
