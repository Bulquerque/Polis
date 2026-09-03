"""Strict, versioned configuration for P6 strategy synthesis."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator

from ..domain.enums import (
    ArchiveMode,
    MutationOperator,
    ObjectiveFamily,
    SolverPortfolioMode,
    TargetPayoffMode,
)
from .artifacts import FrozenModel
from .hashing import utc


class OperationalMode(StrEnum):
    TEMPLATE_ONLY = "TEMPLATE_ONLY"
    TEMPLATE_MUTATION = "TEMPLATE_MUTATION"
    INVERSE_DESIGN = "INVERSE_DESIGN"
    QUALITY_DIVERSITY = "QUALITY_DIVERSITY"
    CHALLENGER = "CHALLENGER"

    @property
    def mutation_enabled(self) -> bool:
        return self is not OperationalMode.TEMPLATE_ONLY

    @property
    def inverse_design_enabled(self) -> bool:
        return self in {
            OperationalMode.INVERSE_DESIGN,
            OperationalMode.QUALITY_DIVERSITY,
            OperationalMode.CHALLENGER,
        }

    @property
    def challenger_enabled(self) -> bool:
        return self is OperationalMode.CHALLENGER


class P5CompatibilityPolicy(FrozenModel):
    policy_version: str = "p5-rc34-native-v2"
    max_distribution_scenarios: int = Field(default=101, ge=1, le=1001)
    # Canonical runs must not silently downgrade to unmanifested legacy P5 inputs.
    # Historical/replay callers can opt in explicitly when required.
    allow_unmanifested_legacy: bool = False
    allow_abstained_beliefs: bool = False
    preferred_horizon_days: int | None = Field(default=None, ge=1, le=3650)
    horizon_time_basis: Literal["CALENDAR_DAYS", "TRADING_DAYS_WEEKDAY"] = "CALENDAR_DAYS"
    # Backward-compatible switch. New runs should use option_expiration_selection.
    require_exact_option_horizon_match: bool = False
    option_expiration_selection: Literal[
        "EXACT", "FIRST_ON_OR_AFTER", "NEAREST"
    ] = "FIRST_ON_OR_AFTER"
    maximum_expiration_gap_days: int = Field(default=45, ge=0, le=3650)


class GenerationBudget(FrozenModel):
    max_contracts_considered: int = Field(default=24, ge=2, le=500)
    max_templates: int = Field(default=16, ge=1, le=100)
    max_mutations: int = Field(default=64, ge=0, le=10_000)
    max_legs: int = Field(default=4, ge=1, le=6)
    max_expirations: int = Field(default=1, ge=1, le=2)
    max_quantity: int = Field(default=2, ge=1, le=10)
    max_solver_seconds: int = Field(default=2, ge=0, le=3_600)
    max_solver_nodes: int = Field(default=2_000, ge=1, le=1_000_000)
    max_memory_mb: int = Field(default=512, ge=64, le=65_536)
    max_candidates_before_dedup: int = Field(default=500, ge=1, le=100_000)
    max_candidates_published: int = Field(default=100, ge=1, le=10_000)
    max_candidates_per_template: int = Field(default=20, ge=1, le=1_000)


class StrategyPolicy(FrozenModel):
    policy_version: str = "wave2-strategy-v1"
    allow_long_underlying: bool = True
    allow_short_underlying: bool = False
    allow_cash_secured_short_put: bool = False
    allow_american_options: bool = False
    enabled_templates: tuple[str, ...] = (
        "LONG_UNDERLYING",
        "LONG_CALL",
        "LONG_PUT",
        "BULL_CALL_DEBIT",
        "BEAR_PUT_DEBIT",
        "BULL_PUT_CREDIT",
        "BEAR_CALL_CREDIT",
        "LONG_STRADDLE",
        "LONG_STRANGLE",
        "LONG_CALL_BUTTERFLY",
        "LONG_CALL_CONDOR",
        "IRON_BUTTERFLY",
        "IRON_CONDOR",
        "COLLAR",
        "RISK_REVERSAL_DEFINED_RISK",
        "PROTECTED_RATIO_CALL",
    )


class MutationPolicy(FrozenModel):
    policy_version: str = "wave2-mutation-v1"
    enabled_operators: tuple[MutationOperator, ...] = (
        MutationOperator.MOVE_STRIKE,
        MutationOperator.CHANGE_QUANTITY,
        MutationOperator.ADD_UNDERLYING,
        MutationOperator.REMOVE_REDUNDANT_LEG,
    )
    max_children_per_parent: int = Field(default=4, ge=0, le=100)
    max_applications_per_candidate: int = Field(default=2, ge=0, le=10)
    allow_underlying_overlay: bool = True
    overlay_quantity: Decimal = Field(default=Decimal("0.25"), gt=0, le=2)
    require_distinct_economic_fingerprint: bool = True


class TargetPayoffPolicy(FrozenModel):
    policy_version: str = "wave2-target-v1"
    modes: tuple[TargetPayoffMode, ...] = (
        TargetPayoffMode.SCENARIO_WEIGHTED,
        TargetPayoffMode.TAIL_HEDGE,
        TargetPayoffMode.RANGE_EXPRESSION,
    )
    objective_families: tuple[ObjectiveFamily, ...] = (
        ObjectiveFamily.DIRECTIONAL_UP,
        ObjectiveFamily.DIRECTIONAL_DOWN,
        ObjectiveFamily.RANGE,
        ObjectiveFamily.LONG_VOLATILITY,
        ObjectiveFamily.TAIL_HEDGE,
    )
    confidence_shrinkage: Decimal = Field(default=Decimal("0.5"), ge=0, le=1)
    smoothing_strength: Decimal = Field(default=Decimal("0.2"), ge=0, le=1)
    clipping_multiple: Decimal = Field(default=Decimal("3"), gt=0, le=100)
    epsilon: Decimal = Field(default=Decimal("0.000001"), gt=0)
    risk_aversion: Decimal = Field(default=Decimal("1"), gt=0)
    tail_probability: Decimal = Field(default=Decimal("0.2"), gt=0, lt=1)
    target_notional: Decimal = Field(default=Decimal("1000"), gt=0)
    minimum_confidence: Decimal = Field(default=Decimal("0.1"), ge=0, le=1)


class SolverPolicy(FrozenModel):
    policy_version: str = "wave2-solver-v1"
    portfolio_mode: SolverPortfolioMode = SolverPortfolioMode.HYBRID
    maximum_basis_size: int = Field(default=12, ge=2, le=100)
    continuous_iterations: int = Field(default=80, ge=1, le=10_000)
    continuous_step_size: Decimal = Field(default=Decimal("0.05"), gt=0, le=1)
    l1_penalty: Decimal = Field(default=Decimal("0.001"), ge=0)
    complexity_penalty: Decimal = Field(default=Decimal("0.01"), ge=0)
    beam_width: int = Field(default=20, ge=1, le=1_000)
    beam_depth: int = Field(default=4, ge=1, le=6)
    local_search_iterations: int = Field(default=50, ge=1, le=10_000)
    evolutionary_population: int = Field(default=20, ge=2, le=1_000)
    evolutionary_generations: int = Field(default=10, ge=1, le=1_000)
    maximum_solutions_per_target: int = Field(default=5, ge=1, le=100)


class PricingPolicy(FrozenModel):
    risk_free_rate: Decimal = Decimal("0.05")
    dividend_yield: Decimal = Decimal("0")
    fee_per_leg: Decimal = Decimal("0")
    slippage_fraction_of_spread: Decimal = Decimal("0.25")
    greek_method: str = "BLACK_SCHOLES_MERTON"
    pathwise_method: str = "BLACK_SCHOLES_PROXY"


class RiskPolicy(FrozenModel):
    require_defined_risk: bool = True
    maximum_loss_limit: Decimal | None = None
    maximum_entry_cost: Decimal | None = None
    minimum_liquidity_score: Decimal = Decimal("0")
    maximum_relative_spread: Decimal = Decimal("1")
    require_complete_liquidity_metrics: bool = True
    allow_degraded_liquidity: bool = False
    require_margin_estimate: bool = True
    ambiguity_probability_shift: Decimal = Field(default=Decimal("0.1"), ge=0, le=0.5)


class PublicationPolicy(FrozenModel):
    representatives_per_niche: int = Field(default=2, ge=1, le=20)
    publish_legacy_p7_projection: bool = True
    archive_mode: ArchiveMode = ArchiveMode.GRID_ARCHIVE
    include_solver_alternatives: bool = True


class Phase6RunConfiguration(FrozenModel):
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    decision_time: datetime
    created_at: datetime
    available_at: datetime
    seed: int = 7
    p5: P5CompatibilityPolicy = P5CompatibilityPolicy()
    operational_mode: OperationalMode = OperationalMode.TEMPLATE_ONLY
    budgets: GenerationBudget = GenerationBudget()
    strategy: StrategyPolicy = StrategyPolicy()
    mutation: MutationPolicy = MutationPolicy()
    target_payoff: TargetPayoffPolicy = TargetPayoffPolicy()
    solver: SolverPolicy = SolverPolicy()
    pricing: PricingPolicy = PricingPolicy()
    risk: RiskPolicy = RiskPolicy()
    publication: PublicationPolicy = PublicationPolicy()

    @field_validator("decision_time", "created_at", "available_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc(value)
