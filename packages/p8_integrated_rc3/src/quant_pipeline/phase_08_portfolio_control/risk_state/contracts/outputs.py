"""Public result, summary, receipt, and Agent-3 handoff contracts."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .base import ArtifactRef, ModuleReceipt, StrictModel
from .enums import (
    ComponentQuality, ConsumptionStatus, MarginFidelity, SizabilityState, ValuationQuality,
)


class PnLCubeSummary(StrictModel):
    candidate_count: int
    leg_count: int
    scenario_count: int
    stress_scenario_count: int
    step_count: int
    pnl_semantics: str
    valuation_quality_by_candidate: dict[str, ValuationQuality]
    content_sha256: str
    storage_npz: str | None = None


class DependenceSummary(StrictModel):
    covariance_method: str
    shrinkage_alpha: float
    effective_sample_size: float
    minimum_eigenvalue_before: float
    minimum_eigenvalue_after: float
    psd_repair_relative: float
    quality: ComponentQuality
    reason_codes: tuple[str, ...] = ()
    content_sha256: str
    storage_npz: str | None = None


class GreekPathSummary(StrictModel):
    greek_coverage_by_candidate: dict[str, float]
    path_capability_by_candidate: dict[str, ComponentQuality]
    dual_book_reconciliation_error: float
    quality: ComponentQuality
    reason_codes: tuple[str, ...] = ()
    content_sha256: str
    storage_npz: str | None = None


class CandidateLiquidityState(StrictModel):
    candidate_id: str
    capacity_units: float | None = Field(default=None, ge=0.0)
    weakest_leg_id: str | None = None
    spread_bps: float | None = Field(default=None, ge=0.0)
    fill_probability_one_unit: float | None = Field(default=None, ge=0.0, le=1.0)
    partial_fill_risk: float | None = Field(default=None, ge=0.0, le=1.0)
    legging_risk: float | None = Field(default=None, ge=0.0, le=1.0)
    fidelity: ComponentQuality
    reason_codes: tuple[str, ...] = ()


class LiquiditySummary(StrictModel):
    states: tuple[CandidateLiquidityState, ...]
    content_sha256: str


class CandidateMarginState(StrictModel):
    candidate_id: str
    margin_per_unit: float | None = Field(default=None, ge=0.0)
    capital_required_per_unit: float | None = Field(default=None, ge=0.0)
    capital_capacity_units: float | None = Field(default=None, ge=0.0)
    borrow_available: bool
    fidelity: MarginFidelity
    quality: ComponentQuality
    capital_quality: ComponentQuality = ComponentQuality.FULLY_QUALIFIED
    reason_codes: tuple[str, ...] = ()


class MarginFundingSummary(StrictModel):
    candidate_states: tuple[CandidateMarginState, ...]
    portfolio_margin_current: float
    margin_headroom: float
    free_cash_after_buffer: float
    eligible_collateral: float
    content_sha256: str


class CandidateSizability(StrictModel):
    candidate_id: str
    state: SizabilityState
    max_units: float | None = Field(default=None, ge=0.0)
    liquidity_max_units: float | None = Field(default=None, ge=0.0)
    capital_max_units: float | None = Field(default=None, ge=0.0)
    risk_budget_cap: float = Field(ge=0.0, le=1.0)
    component_quality: dict[str, ComponentQuality]
    reason_codes: tuple[str, ...] = ()


class RiskCapabilityReceipt(StrictModel):
    artifact_status: dict[str, ConsumptionStatus]
    candidate_status: dict[str, SizabilityState]
    reason_codes: tuple[str, ...] = ()


class P8DecisionReadyRiskBundle(StrictModel):
    bundle_id: str
    run_id: str
    cycle_id: str
    decision_time: datetime
    s3_result_sha256: str
    pnl_cube_ref: ArtifactRef
    dependence_state_ref: ArtifactRef
    greek_path_state_ref: ArtifactRef
    liquidity_state_ref: ArtifactRef
    margin_funding_state_ref: ArtifactRef
    candidate_sizability: tuple[CandidateSizability, ...]
    risk_capability_receipt: RiskCapabilityReceipt
    content_sha256: str


class S4Result(StrictModel):
    run_id: str
    cycle_id: str
    pnl_cube: PnLCubeSummary
    dependence: DependenceSummary
    greek_path: GreekPathSummary
    liquidity: LiquiditySummary
    margin_funding: MarginFundingSummary
    candidate_sizability: tuple[CandidateSizability, ...]
    risk_capability_receipt: RiskCapabilityReceipt
    bundle: P8DecisionReadyRiskBundle
    receipts: tuple[ModuleReceipt, ...]
    result_sha256: str
