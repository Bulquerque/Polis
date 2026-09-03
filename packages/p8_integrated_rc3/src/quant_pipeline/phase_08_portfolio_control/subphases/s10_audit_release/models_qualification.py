from __future__ import annotations
from decimal import Decimal
from typing import Literal
from pydantic import Field, model_validator
from .enums import (CycleTerminalState, EconomicQualification, ImplementationRobustness,
    ReasonCode, StatisticalQualification, TechnicalValidity)
from .models_audit import IndependentAuditReport
from .models_common import AuditContext, StrictModel

class RobustnessEvidence(StrictModel):
    clean_replay_passed: bool
    clean_install_passed: bool
    clean_extraction_passed: bool
    consumer_contracts_passed: bool
    golden_threads_required: tuple[str, ...]
    golden_threads_passed: tuple[str, ...]
    perturbations_required: int = Field(ge=0)
    perturbations_passed: int = Field(ge=0)
    @model_validator(mode="after")
    def counts_valid(self) -> "RobustnessEvidence":
        if self.perturbations_passed > self.perturbations_required:
            raise ValueError("perturbations_passed cannot exceed required")
        return self

class StatisticalEvidence(StrictModel):
    returns: tuple[Decimal, ...] = ()
    periods_per_year: int = Field(default=252, gt=0)
    trial_sharpes: tuple[Decimal, ...] = ()
    strategy_returns: tuple[tuple[Decimal, ...], ...] = ()
    trial_registry_complete: bool
    holdout_preserved: bool
    minimum_observations: int = Field(default=30, ge=2)
    dsr_threshold: Decimal = Field(default=Decimal("0.95"), ge=0, le=1)
    pbo_threshold: Decimal = Field(default=Decimal("0.50"), ge=0, le=1)

class StatisticalDiagnostics(StrictModel):
    observation_count: int = Field(ge=0)
    sharpe_ratio: Decimal | None
    deflated_sharpe_ratio: Decimal | None
    probability_backtest_overfitting: Decimal | None

class QualificationRequest(StrictModel):
    context: AuditContext
    terminal_state: CycleTerminalState
    audit_report: IndependentAuditReport
    robustness: RobustnessEvidence
    statistical: StatisticalEvidence

class QualificationDecision(StrictModel):
    qualification_id: str = Field(min_length=1)
    context: AuditContext
    terminal_state: CycleTerminalState
    technical_validity: TechnicalValidity
    implementation_robustness: ImplementationRobustness
    statistical_qualification: StatisticalQualification
    economic_qualification: EconomicQualification = EconomicQualification.DEFERRED_TO_P9
    diagnostics: StatisticalDiagnostics
    reason_codes: tuple[ReasonCode, ...]
    eligible_for_p9_evaluation: bool
    production_promotion_allowed: Literal[False] = False
