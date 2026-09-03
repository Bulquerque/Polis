from __future__ import annotations

from quant_pipeline.phase_09.subphases.s04_performance_risk.distribution_models import DistributionEngineRequest
from quant_pipeline.phase_09.subphases.s04_performance_risk.drawdown_models import DrawdownRequest
from quant_pipeline.phase_09.subphases.s04_performance_risk.m01_returns import compute_returns
from quant_pipeline.phase_09.subphases.s04_performance_risk.m02_distribution import compute_distribution
from quant_pipeline.phase_09.subphases.s04_performance_risk.m04_drawdown import compute_drawdowns
from quant_pipeline.phase_09.subphases.s04_performance_risk.m05_risk_adjusted import compute_risk_adjusted
from quant_pipeline.phase_09.subphases.s04_performance_risk.return_models import ReturnEngineRequest
from quant_pipeline.phase_09.subphases.s04_performance_risk.risk_adjusted_models import RiskAdjustedRequest


def find(panel, metric_id):
    return next(metric for metric in panel.metrics if metric.metric_id == metric_id)


def build(qualified, policies, benchmark, risk_free):
    returns = compute_returns(
        ReturnEngineRequest(
            qualified_backtest=qualified,
            policy=policies["return"],
            benchmark=benchmark,
            risk_free=risk_free,
        )
    )
    distribution = compute_distribution(
        DistributionEngineRequest(returns=returns.return_series, policy=policies["distribution"])
    )
    drawdown = compute_drawdowns(
        DrawdownRequest(wealth_path=returns.wealth_path, policy=policies["drawdown"])
    )
    result = compute_risk_adjusted(
        RiskAdjustedRequest(
            returns=returns,
            distribution=distribution,
            drawdown=drawdown.metrics,
            policy=policies["risk_adjusted"],
            benchmark=benchmark,
            risk_free=risk_free,
        )
    )
    return result


def test_risk_adjusted_metrics(qualified, policies, benchmark, risk_free):
    result = build(qualified, policies, benchmark, risk_free)
    assert find(result.metrics, "ratio.sharpe").value is not None
    assert find(result.metrics, "ratio.psr").value is not None
    assert 0 <= find(result.metrics, "ratio.psr").value <= 1
    assert find(result.metrics, "ratio.calmar").value is not None
    assert find(result.metrics, "ratio.information").value is not None


def test_autocorrelation_adjustment_is_explicit(qualified, policies, benchmark, risk_free):
    result = build(qualified, policies, benchmark, risk_free)
    factor = result.sharpe_diagnostics.autocorrelation_adjustment_factor
    assert factor is not None and factor > 0
    assert find(result.metrics, "ratio.sharpe_autocorrelation_adjusted").value is not None


def test_missing_risk_free_is_limited_not_fabricated(qualified, policies):
    returns = compute_returns(ReturnEngineRequest(qualified_backtest=qualified, policy=policies["return"]))
    distribution = compute_distribution(
        DistributionEngineRequest(returns=returns.return_series, policy=policies["distribution"])
    )
    drawdown = compute_drawdowns(DrawdownRequest(wealth_path=returns.wealth_path, policy=policies["drawdown"]))
    result = compute_risk_adjusted(
        RiskAdjustedRequest(
            returns=returns,
            distribution=distribution,
            drawdown=drawdown.metrics,
            policy=policies["risk_adjusted"],
        )
    )
    assert "P9_S4_RISK_FREE_UNAVAILABLE" in result.metrics.limitations
