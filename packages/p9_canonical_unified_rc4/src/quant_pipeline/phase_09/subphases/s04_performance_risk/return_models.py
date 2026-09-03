"""Return and wealth-path contracts for P9.S4.M01."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.integrity_models import (
    BacktestQualificationReceipt,
    P8EvaluationHandoff,
    QualificationState,
)

from .base_models import (
    AnnualizationPolicy,
    ModulePanelBase,
    PointInTimeSeries,
    QualifiedBacktestIdentity,
    timestamps_are_strictly_ordered,
)
from .common import (
    FiniteDecimal,
    FiniteFloat,
    NonEmptyStr,
    ReturnConvention,
    SemVer,
    Sha256,
    StrictModel,
    UtcDateTime,
    content_sha256,
)


class ExternalFlowTiming(StrEnum):
    END_OF_PERIOD = "END_OF_PERIOD"


class ReturnPolicy(StrictModel):
    policy_id: NonEmptyStr
    policy_version: SemVer
    convention: ReturnConvention = ReturnConvention.SIMPLE
    external_flow_timing: ExternalFlowTiming = ExternalFlowTiming.END_OF_PERIOD
    annualization: AnnualizationPolicy
    require_benchmark_alignment: bool = False
    require_risk_free_alignment: bool = False


class QualifiedBacktestInput(StrictModel):
    configuration_id: NonEmptyStr
    handoff: P8EvaluationHandoff
    qualification: BacktestQualificationReceipt

    @model_validator(mode="after")
    def validate_qualification(self) -> Self:
        if self.qualification.handoff_id != self.handoff.handoff_id:
            raise ValueError("qualification and handoff IDs must match")
        if self.qualification.state not in {
            QualificationState.QUALIFIED,
            QualificationState.NO_ACTION_VALID,
        }:
            raise ValueError("S4 accepts only QUALIFIED or NO_ACTION_VALID backtests")
        if self.qualification.qualified_handoff_sha256 != self.handoff.replay_sha256:
            raise ValueError("qualified handoff hash must match replay hash")
        return self

    def identity(self) -> QualifiedBacktestIdentity:
        return QualifiedBacktestIdentity(
            run_id=self.handoff.run_id,
            cycle_id=self.handoff.cycle_id,
            trial_id=self.handoff.trial_id,
            fold_id=self.handoff.fold_id,
            configuration_id=self.configuration_id,
            handoff_id=self.handoff.handoff_id,
            handoff_sha256=self.handoff.replay_sha256,
        )


class ReturnEngineRequest(StrictModel):
    qualified_backtest: QualifiedBacktestInput
    policy: ReturnPolicy
    benchmark: PointInTimeSeries | None = None
    risk_free: PointInTimeSeries | None = None

    @model_validator(mode="after")
    def validate_required_series(self) -> Self:
        if self.policy.require_benchmark_alignment and self.benchmark is None:
            raise ValueError("benchmark series is required by policy")
        if self.policy.require_risk_free_alignment and self.risk_free is None:
            raise ValueError("risk-free series is required by policy")
        return self


class WealthPoint(StrictModel):
    timestamp: UtcDateTime
    nav: FiniteDecimal
    gross_wealth: FiniteDecimal
    net_wealth: FiniteDecimal
    external_flow: FiniteDecimal
    period_cost: FiniteDecimal = Field(ge=Decimal("0"))
    cumulative_cost: FiniteDecimal = Field(ge=Decimal("0"))
    gross_return: FiniteFloat | None
    net_return: FiniteFloat | None
    benchmark_return: FiniteFloat | None = None
    risk_free_return: FiniteFloat | None = None
    active_return: FiniteFloat | None = None
    excess_return: FiniteFloat | None = None


class WealthPathPanel(ModulePanelBase):
    points: tuple[WealthPoint, ...]
    return_convention: ReturnConvention
    periods_per_year: FiniteFloat

    @model_validator(mode="after")
    def validate_panel(self) -> Self:
        if not self.points:
            raise ValueError("wealth path requires at least one point")
        timestamps = tuple(point.timestamp for point in self.points)
        if not timestamps_are_strictly_ordered(timestamps):
            raise ValueError("wealth points must be strictly time ordered")
        expected = content_sha256(self.hash_preimage())
        if expected != self.content_sha256:
            raise ValueError("wealth path content hash mismatch")
        return self


class ReturnSeriesPanel(ModulePanelBase):
    timestamps: tuple[UtcDateTime, ...]
    gross_returns: tuple[FiniteFloat, ...]
    net_returns: tuple[FiniteFloat, ...]
    active_returns: tuple[FiniteFloat, ...] | None = None
    excess_returns: tuple[FiniteFloat, ...] | None = None
    periods_per_year: FiniteFloat

    @model_validator(mode="after")
    def validate_panel(self) -> Self:
        if not timestamps_are_strictly_ordered(self.timestamps):
            raise ValueError("return timestamps must be strictly ordered")
        expected_length = len(self.timestamps)
        if len(self.gross_returns) != expected_length or len(self.net_returns) != expected_length:
            raise ValueError("return arrays must match timestamps")
        for optional in (self.active_returns, self.excess_returns):
            if optional is not None and len(optional) != expected_length:
                raise ValueError("optional return arrays must match timestamps")
        expected = content_sha256(self.hash_preimage())
        if expected != self.content_sha256:
            raise ValueError("return series content hash mismatch")
        return self


class ReturnMetricPanel(ModulePanelBase):
    start_nav: FiniteDecimal
    end_nav: FiniteDecimal
    total_external_flow: FiniteDecimal
    total_cost: FiniteDecimal = Field(ge=Decimal("0"))

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        expected = content_sha256(self.hash_preimage())
        if expected != self.content_sha256:
            raise ValueError("return metric panel hash mismatch")
        return self


class ReturnEngineResult(StrictModel):
    wealth_path: WealthPathPanel
    return_series: ReturnSeriesPanel
    return_metrics: ReturnMetricPanel
    reconciliation_sha256: Sha256
