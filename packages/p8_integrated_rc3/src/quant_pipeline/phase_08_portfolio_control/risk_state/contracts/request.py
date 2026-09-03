"""Top-level S4 request contract with cross-artifact validation."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from .base import S3Result, StrictModel
from .candidates import CandidateEconomicPackage, CandidatePosition, FactorDefinition, PhysicalPosition
from .market import AccountState, BorrowRecord, MarginRules, MarketLiquiditySnapshot, ScenarioArtifactBundle
from .policies import (
    DependencePolicy, GreekPolicy, LiquidityPolicy, MarginPolicy, PnLPolicy, ReconciliationPolicy,
)


class S4Request(StrictModel):
    run_id: str
    cycle_id: str
    decision_time: datetime
    s3_result: S3Result
    scenario_artifacts: ScenarioArtifactBundle
    candidates: tuple[CandidateEconomicPackage, ...]
    factor_definitions: tuple[FactorDefinition, ...]
    step_year_fractions: tuple[float, ...] = Field(min_length=1)
    current_candidate_positions: tuple[CandidatePosition, ...] = ()
    physical_positions: tuple[PhysicalPosition, ...] = ()
    liquidity_snapshot: MarketLiquiditySnapshot
    account_state: AccountState
    borrow_records: tuple[BorrowRecord, ...] = ()
    margin_rules: MarginRules
    pnl_policy: PnLPolicy = PnLPolicy()
    dependence_policy: DependencePolicy = DependencePolicy()
    greek_policy: GreekPolicy = GreekPolicy()
    liquidity_policy: LiquidityPolicy = LiquidityPolicy()
    margin_policy: MarginPolicy = MarginPolicy()
    reconciliation_policy: ReconciliationPolicy = ReconciliationPolicy()

    @model_validator(mode="after")
    def validate_request(self) -> "S4Request":
        if self.decision_time.tzinfo is None:
            raise ValueError("decision_time must be timezone-aware")
        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate_id must be unique")
        factor_ids = [factor.factor_id for factor in self.factor_definitions]
        if len(factor_ids) != len(set(factor_ids)):
            raise ValueError("factor definitions must be unique")
        if any(value < 0.0 for value in self.step_year_fractions):
            raise ValueError("step_year_fractions must be nonnegative")
        if tuple(sorted(self.step_year_fractions)) != self.step_year_fractions:
            raise ValueError("step_year_fractions must be nondecreasing")
        currencies = {candidate.currency for candidate in self.candidates}
        if self.candidates and (len(currencies) != 1 or self.account_state.currency not in currencies):
            raise ValueError("multi-currency S4 requires an explicit FX adapter")
        return self
