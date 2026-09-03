"""Composed S4 analytics service with explicit policies and optional capabilities."""

from __future__ import annotations

from pydantic import model_validator

from .base_models import PointInTimeSeries
from .bundle_models import MetricQualityPolicy, MetricQualityRequest, MetricQualityResult, MetricRegistry
from .common import StrictModel
from .distribution_models import DistributionEngineRequest, DistributionEngineResult, DistributionPolicy
from .drawdown_models import DrawdownPolicy, DrawdownRequest, DrawdownResult
from .execution_models import (
    CapacityPolicy,
    ExecutionCapacityResult,
    ExecutionCapacityRequest,
    ExposureSnapshot,
    LiquidityObservation,
    TargetOrderContext,
)
from .factor_models import (
    BenchmarkAndFactorPanel,
    FactorModelRegistry,
    FactorRegressionRequest,
    FactorRegressionResult,
    RegressionPolicy,
)
from .m01_returns import compute_returns
from .m02_distribution import compute_distribution
from .m03_tail_risk import compute_tail_risk
from .m04_drawdown import compute_drawdowns
from .m05_risk_adjusted import compute_risk_adjusted
from .m06_factor_regression import compute_factor_regressions
from .m07_execution_capacity import compute_execution_capacity
from .m08_quality_gate import reconcile_metrics
from .return_models import QualifiedBacktestInput, ReturnEngineRequest, ReturnEngineResult, ReturnPolicy
from .risk_adjusted_models import RiskAdjustedMetricPolicy, RiskAdjustedRequest, RiskAdjustedResult
from .tail_models import ScenarioPnlPanel, TailRiskPolicy, TailRiskRequest, TailRiskResult


class S4AnalyticsRequest(StrictModel):
    qualified_backtest: QualifiedBacktestInput
    return_policy: ReturnPolicy
    distribution_policy: DistributionPolicy
    tail_policy: TailRiskPolicy
    drawdown_policy: DrawdownPolicy
    risk_adjusted_policy: RiskAdjustedMetricPolicy
    capacity_policy: CapacityPolicy
    metric_registry: MetricRegistry
    metric_quality_policy: MetricQualityPolicy
    benchmark: PointInTimeSeries | None = None
    risk_free: PointInTimeSeries | None = None
    scenarios: ScenarioPnlPanel | None = None
    factor_panel: BenchmarkAndFactorPanel | None = None
    factor_registry: FactorModelRegistry | None = None
    regression_policy: RegressionPolicy | None = None
    target_contexts: tuple[TargetOrderContext, ...] = ()
    liquidity: tuple[LiquidityObservation, ...] = ()
    exposures: tuple[ExposureSnapshot, ...] = ()

    @model_validator(mode="after")
    def validate_factor_inputs(self):
        supplied = (
            self.factor_panel is not None,
            self.factor_registry is not None,
            self.regression_policy is not None,
        )
        if any(supplied) and not all(supplied):
            raise ValueError("factor panel, registry, and regression policy must be supplied together")
        return self


class S4AnalyticsResult(StrictModel):
    returns: ReturnEngineResult
    distribution: DistributionEngineResult
    tails: TailRiskResult
    drawdowns: DrawdownResult
    risk_adjusted: RiskAdjustedResult
    factors: FactorRegressionResult | None
    execution: ExecutionCapacityResult
    quality: MetricQualityResult


class S4AnalyticsService:
    """Execute M01→M08 while preserving authority boundaries between modules."""

    def run(self, request: S4AnalyticsRequest) -> S4AnalyticsResult:
        returns = compute_returns(
            ReturnEngineRequest(
                qualified_backtest=request.qualified_backtest,
                policy=request.return_policy,
                benchmark=request.benchmark,
                risk_free=request.risk_free,
            )
        )
        distribution = compute_distribution(
            DistributionEngineRequest(returns=returns.return_series, policy=request.distribution_policy)
        )
        tails = compute_tail_risk(
            TailRiskRequest(returns=returns.return_series, policy=request.tail_policy, scenarios=request.scenarios)
        )
        drawdowns = compute_drawdowns(
            DrawdownRequest(wealth_path=returns.wealth_path, policy=request.drawdown_policy)
        )
        risk_adjusted = compute_risk_adjusted(
            RiskAdjustedRequest(
                returns=returns,
                distribution=distribution,
                drawdown=drawdowns.metrics,
                policy=request.risk_adjusted_policy,
                benchmark=request.benchmark,
                risk_free=request.risk_free,
            )
        )
        factors = None
        if request.factor_panel is not None and request.factor_registry is not None and request.regression_policy is not None:
            if request.risk_free is None:
                raise ValueError("factor regression requires risk-free series")
            factors = compute_factor_regressions(
                FactorRegressionRequest(
                    returns=returns.return_series,
                    factors=request.factor_panel,
                    risk_free=request.risk_free,
                    registry=request.factor_registry,
                    policy=request.regression_policy,
                )
            )
        net_cumulative = next(
            (
                metric.value
                for metric in returns.return_metrics.metrics
                if metric.metric_id == "return.cumulative" and metric.gross_net.value == "NET"
            ),
            None,
        )
        execution = compute_execution_capacity(
            ExecutionCapacityRequest(
                identity=returns.return_series.identity,
                handoff=request.qualified_backtest.handoff,
                target_contexts=request.target_contexts,
                liquidity=request.liquidity,
                exposures=request.exposures,
                policy=request.capacity_policy,
                baseline_net_return=net_cumulative,
            )
        )
        quality = reconcile_metrics(
            MetricQualityRequest(
                returns=returns,
                distribution=distribution,
                tails=tails,
                drawdowns=drawdowns,
                risk_adjusted=risk_adjusted,
                factors=factors,
                execution=execution,
                registry=request.metric_registry,
                policy=request.metric_quality_policy,
            )
        )
        return S4AnalyticsResult(
            returns=returns,
            distribution=distribution,
            tails=tails,
            drawdowns=drawdowns,
            risk_adjusted=risk_adjusted,
            factors=factors,
            execution=execution,
            quality=quality,
        )
