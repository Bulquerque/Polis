"""Canonical payoff, scenario, risk, quality, and capability models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, JsonValue, field_validator

from ..foundation.artifacts import FrozenModel
from ..foundation.hashing import utc
from .enums import (
    CalculationStatus,
    CapabilityStatus,
    MarginMethod,
    ObjectiveFamily,
    TemplateId,
)


class TargetPayoff(FrozenModel):
    """Wave 2 target-payoff contract; capability is unavailable in Wave 1."""

    target_payoff_id: str
    underlying_id: str
    decision_time: datetime
    horizon_days: int = Field(gt=0)
    objective_family: ObjectiveFamily
    terminal_state_grid: tuple[Decimal, ...]
    desired_payoff: tuple[Decimal, ...]
    desired_wealth_distribution: tuple[Decimal, ...] = ()
    path_constraints: dict[str, JsonValue] = Field(default_factory=dict)
    tail_constraints: dict[str, JsonValue] = Field(default_factory=dict)
    cost_budget: Decimal | None = Field(default=None, ge=0)
    risk_budget: Decimal | None = Field(default=None, ge=0)
    complexity_budget: int | None = Field(default=None, ge=1)
    belief_state_id: str
    ambiguity_set_id: str | None = None

    @field_validator("decision_time")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc(value)


class StrategyPayoffRecord(FrozenModel):
    candidate_id: str
    spot_grid: tuple[Decimal, ...]
    terminal_pnl: tuple[Decimal, ...]
    entry_cash_flow: Decimal
    maximum_loss: Decimal | None
    maximum_gain: Decimal | None
    maximum_gain_unbounded: bool
    break_even_points: tuple[Decimal, ...]
    right_tail_slope: Decimal
    payoff_status: CalculationStatus


class ScenarioProbabilityMassAuditRecord(FrozenModel):
    """Auditable probability-mass transformation performed at the P5→P6 boundary."""

    belief_state_id: str = Field(min_length=1)
    underlying_id: str = Field(min_length=1)
    horizon_days: int = Field(gt=0)
    method: str = Field(min_length=1)
    source_scenario_count: int = Field(ge=0)
    retained_scenario_count: int = Field(ge=0)
    original_probability_mass: Decimal = Field(ge=0)
    retained_probability_mass: Decimal = Field(ge=0)
    rejected_probability_mass: Decimal = Field(ge=0)
    normalization_factor: Decimal | None = Field(default=None, gt=0)
    renormalized: bool


class ScenarioEvaluation(FrozenModel):
    candidate_id: str
    scenario_id: str
    scenario_probability: Decimal = Field(ge=0, le=1)
    terminal_payoff: Decimal
    pathwise_mark_to_market: tuple[Decimal, ...] = ()
    maximum_path_loss: Decimal | None = None
    margin_stress: Decimal | None = None
    liquidity_stress: Decimal | None = None
    exercise_state: str = "NOT_MODELLED"
    assignment_state: str = "NOT_MODELLED"
    scenario_cost: Decimal
    scenario_pnl: Decimal


class CandidateRiskSummary(FrozenModel):
    candidate_id: str
    expected_net_payoff: Decimal
    median_net_payoff: Decimal
    probability_of_profit: Decimal = Field(ge=0, le=1)
    lower_quantile: Decimal
    upper_quantile: Decimal
    value_at_risk: Decimal
    expected_shortfall: Decimal
    maximum_loss: Decimal | None
    maximum_gain: Decimal | None
    return_on_max_loss: Decimal | None
    return_on_margin: Decimal | None
    break_even_points: tuple[Decimal, ...]
    nominal_utility: Decimal | None = None
    worst_ambiguity_utility: Decimal | None = None
    regret: Decimal | None = None


class GreekState(FrozenModel):
    candidate_id: str
    delta: Decimal | None
    gamma: Decimal | None
    vega: Decimal | None
    theta: Decimal | None
    rho: Decimal | None = None
    vanna: Decimal | None = None
    volga: Decimal | None = None
    charm: Decimal | None = None
    calculation_method: str
    calculation_time: datetime
    input_surface_id: str | None = None
    status: CalculationStatus

    @field_validator("calculation_time")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc(value)


class CostLiquidityRecord(FrozenModel):
    candidate_id: str
    quoted_cost: Decimal
    conservative_entry_cost: Decimal
    stress_entry_cost: Decimal
    fee_estimate: Decimal
    slippage_estimate: Decimal
    weakest_leg_liquidity: Decimal | None
    maximum_relative_spread: Decimal | None
    atomic_combo_available: bool
    legging_required: bool
    legging_risk_proxy: Decimal | None
    status: CalculationStatus


class CandidateQualification(FrozenModel):
    candidate_id: str
    qualified: bool
    reason_codes: tuple[str, ...]
    maximum_loss_proven: bool
    margin_method: MarginMethod
    margin_estimate: Decimal | None
    margin_scope: str = "STANDALONE_CANDIDATE"
    margin_confidence: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    margin_status: CalculationStatus = CalculationStatus.UNAVAILABLE
    data_quality_status: CalculationStatus


class CandidateEquivalence(FrozenModel):
    candidate_id: str
    leg_shape_fingerprint: str
    payoff_fingerprint: str
    economic_fingerprint: str
    equivalence_cluster_id: str
    relative_scale: Decimal
    representative: bool = False


class QualityDiversityCell(FrozenModel):
    niche_id: str
    objective_family: ObjectiveFamily
    leg_count: int = Field(gt=0)
    risk_bucket: str
    candidate_ids: tuple[str, ...]
    representative_candidate_ids: tuple[str, ...]


class RejectionRecord(FrozenModel):
    rejection_id: str
    candidate_id: str | None = None
    template_id: TemplateId | None = None
    stage: str
    reason_code: str
    details: dict[str, JsonValue]


class GenerationAudit(FrozenModel):
    generation_run_id: str
    attempted_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    qualified_count: int = Field(ge=0)
    published_count: int = Field(ge=0)
    seed: int
    policy_version: str


class CapabilityRecord(FrozenModel):
    capability: str
    status: CapabilityStatus
    reason_code: str
    planned_wave: int = Field(ge=1)


class StrategyShapeRecord(FrozenModel):
    candidate_id: str
    break_even_points: tuple[Decimal, ...]
    profit_intervals: tuple[tuple[Decimal, Decimal], ...]
    loss_intervals: tuple[tuple[Decimal, Decimal], ...]
    bounded_below: bool
    maximum_gain_unbounded: bool
    right_tail_slope: Decimal
    discontinuities: tuple[Decimal, ...] = ()


class AmbiguityEvaluationRecord(FrozenModel):
    candidate_id: str
    status: CapabilityStatus
    worst_case_expected_payoff: Decimal | None = None
    worst_case_expected_utility: Decimal | None = None
    worst_case_cvar: Decimal | None = None
    ambiguity_regret: Decimal | None = None
    distribution_sensitivity: Decimal | None = None
    reason_code: str = "P6_CAPABILITY_UNAVAILABLE"


