"""Execution, cost, exposure, and capacity contracts for P9.S4.M07."""

from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import Field, model_validator

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.integrity_models import (
    P8EvaluationHandoff,
)

from .base_models import ModulePanelBase, QualifiedBacktestIdentity
from .common import (
    EvidenceClass,
    FiniteDecimal,
    FiniteFloat,
    NonEmptyStr,
    SemVer,
    StrictModel,
    UtcDateTime,
    content_sha256,
)


class TargetOrderContext(StrictModel):
    target_id: NonEmptyStr
    order_id: NonEmptyStr
    instrument_id: NonEmptyStr
    target_quantity: FiniteDecimal
    arrival_price: FiniteDecimal = Field(gt=Decimal("0"))
    decision_time: UtcDateTime
    bid_price: FiniteDecimal | None = Field(default=None, gt=Decimal("0"))
    ask_price: FiniteDecimal | None = Field(default=None, gt=Decimal("0"))

    @model_validator(mode="after")
    def validate_quotes(self) -> Self:
        if (self.bid_price is None) != (self.ask_price is None):
            raise ValueError("bid and ask must be supplied together")
        if self.bid_price is not None and self.ask_price is not None:
            if self.bid_price > self.ask_price:
                raise ValueError("bid cannot exceed ask")
        return self


class LiquidityObservation(StrictModel):
    instrument_id: NonEmptyStr
    timestamp: UtcDateTime
    available_at: UtcDateTime
    average_daily_volume: FiniteDecimal = Field(gt=Decimal("0"))
    daily_volatility: FiniteFloat = Field(gt=0)
    mid_price: FiniteDecimal = Field(gt=Decimal("0"))

    @model_validator(mode="after")
    def validate_pit(self) -> Self:
        if self.available_at > self.timestamp:
            raise ValueError("liquidity observation must be available by timestamp")
        return self


class ExposureSnapshot(StrictModel):
    timestamp: UtcDateTime
    gross_exposure: FiniteDecimal = Field(ge=Decimal("0"))
    net_exposure: FiniteDecimal
    margin_used: FiniteDecimal = Field(ge=Decimal("0"))
    nav: FiniteDecimal = Field(gt=Decimal("0"))


class ImpactPolicy(StrictModel):
    policy_id: NonEmptyStr
    policy_version: SemVer
    evidence_class: EvidenceClass = EvidenceClass.PARAMETRIC_IMPACT
    eta: FiniteFloat = Field(default=0.10, ge=0)
    maximum_participation: FiniteFloat = Field(default=0.20, gt=0, le=1)


class CapacityPolicy(StrictModel):
    policy_id: NonEmptyStr
    policy_version: SemVer
    aum_multipliers: tuple[FiniteFloat, ...] = (0.5, 1.0, 2.0, 5.0)
    impact: ImpactPolicy

    @model_validator(mode="after")
    def validate_multipliers(self) -> Self:
        if any(value <= 0 for value in self.aum_multipliers):
            raise ValueError("AUM multipliers must be positive")
        if len(set(self.aum_multipliers)) != len(self.aum_multipliers):
            raise ValueError("AUM multipliers must be unique")
        return self


class ExecutionMetricRecord(StrictModel):
    metric_id: NonEmptyStr
    value: FiniteFloat | None
    status: NonEmptyStr
    evidence_class: EvidenceClass
    observation_count: int = Field(ge=0)
    limitations: tuple[NonEmptyStr, ...] = ()


class CapacityPoint(StrictModel):
    aum_multiplier: FiniteFloat = Field(gt=0)
    estimated_impact_fraction: FiniteFloat = Field(ge=0)
    estimated_net_return_after_impact: FiniteFloat | None
    maximum_participation_fraction: FiniteFloat = Field(ge=0)
    status: NonEmptyStr


class ExecutionMetricPanel(ModulePanelBase):
    execution_metrics: tuple[ExecutionMetricRecord, ...]

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("execution metric panel hash mismatch")
        return self


class CostDragPanel(ModulePanelBase):
    total_fees: FiniteDecimal = Field(ge=Decimal("0"))
    total_financing: FiniteDecimal
    total_borrow: FiniteDecimal
    observed_slippage: FiniteDecimal | None

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("cost drag panel hash mismatch")
        return self


class CapacityCurvePanel(ModulePanelBase):
    points: tuple[CapacityPoint, ...]
    evidence_class: EvidenceClass

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("capacity curve hash mismatch")
        return self


class ExecutionCapacityRequest(StrictModel):
    identity: QualifiedBacktestIdentity
    handoff: P8EvaluationHandoff
    target_contexts: tuple[TargetOrderContext, ...] = ()
    liquidity: tuple[LiquidityObservation, ...] = ()
    exposures: tuple[ExposureSnapshot, ...] = ()
    policy: CapacityPolicy
    baseline_net_return: FiniteFloat | None = None


class ExecutionCapacityResult(StrictModel):
    execution: ExecutionMetricPanel
    costs: CostDragPanel
    capacity: CapacityCurvePanel
