from __future__ import annotations

import numpy as np
import pytest

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.contracts import MetricDefinition, MetricName
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.metric_registry import (
    MetricCalculatorRegistry,
    MetricContext,
    MetricEvaluationError,
    alpha,
    annualized_return,
    beta,
    cagr,
    calmar,
    cumulative_return,
    expected_shortfall,
    information_ratio,
    max_drawdown,
    sharpe,
    sortino,
    volatility,
)


def definition(name: MetricName) -> MetricDefinition:
    return MetricDefinition(metric_id=name.value.lower(), metric_name=name, target_series_id="strategy")


def test_all_builtin_metrics_return_finite_values() -> None:
    returns = np.asarray([0.01, -0.02, 0.03, -0.005, 0.015], dtype=np.float64)
    benchmark = np.asarray([0.005, -0.01, 0.01, 0.0, 0.005], dtype=np.float64)
    risk_free = np.full(5, 0.0001)
    context = MetricContext(returns=returns, periods_per_year=252.0, benchmark=benchmark, risk_free=risk_free)
    functions = {
        MetricName.ANNUALIZED_RETURN: annualized_return,
        MetricName.VOLATILITY: volatility,
        MetricName.SHARPE: sharpe,
        MetricName.CUMULATIVE_RETURN: cumulative_return,
        MetricName.CAGR: cagr,
        MetricName.MAX_DRAWDOWN: max_drawdown,
        MetricName.SORTINO: sortino,
        MetricName.CALMAR: calmar,
        MetricName.EXPECTED_SHORTFALL: expected_shortfall,
        MetricName.ALPHA: alpha,
        MetricName.BETA: beta,
        MetricName.INFORMATION_RATIO: information_ratio,
    }
    for name, function in functions.items():
        assert np.isfinite(function(context, definition(name)))


def test_metric_error_branches_are_explicit() -> None:
    one = MetricContext(returns=np.asarray([0.01]), periods_per_year=252.0)
    constant = MetricContext(returns=np.ones(4) * 0.01, periods_per_year=252.0)
    with pytest.raises(MetricEvaluationError): volatility(one, definition(MetricName.VOLATILITY))
    with pytest.raises(MetricEvaluationError): sharpe(one, definition(MetricName.SHARPE))
    with pytest.raises(MetricEvaluationError): sharpe(constant, definition(MetricName.SHARPE))
    with pytest.raises(MetricEvaluationError): cagr(MetricContext(returns=np.asarray([-2.0]), periods_per_year=252.0), definition(MetricName.CAGR))
    with pytest.raises(MetricEvaluationError): sortino(MetricContext(returns=np.asarray([0.01, 0.02]), periods_per_year=252.0), definition(MetricName.SORTINO))
    with pytest.raises(MetricEvaluationError): calmar(MetricContext(returns=np.asarray([0.01, 0.02]), periods_per_year=252.0), definition(MetricName.CALMAR))
    with pytest.raises(MetricEvaluationError): beta(constant, definition(MetricName.BETA))
    no_benchmark = MetricContext(returns=np.asarray([0.01, -0.01]), periods_per_year=252.0)
    with pytest.raises(MetricEvaluationError): beta(no_benchmark, definition(MetricName.BETA))
    with pytest.raises(MetricEvaluationError): alpha(no_benchmark, definition(MetricName.ALPHA))
    with pytest.raises(MetricEvaluationError): information_ratio(no_benchmark, definition(MetricName.INFORMATION_RATIO))
    same = MetricContext(returns=np.asarray([0.01, -0.01]), benchmark=np.asarray([0.01, -0.01]), periods_per_year=252.0)
    with pytest.raises(MetricEvaluationError): information_ratio(same, definition(MetricName.INFORMATION_RATIO))


def test_registry_rejects_duplicate_missing_and_nonfinite_calculators() -> None:
    registry = MetricCalculatorRegistry()
    with pytest.raises(ValueError, match="already registered"):
        registry.register(MetricName.SHARPE, lambda c, d: 0.0)
    context = MetricContext(returns=np.asarray([0.01, -0.01]), periods_per_year=252.0)
    with pytest.raises(MetricEvaluationError, match="upstream"):
        registry.evaluate(context, definition(MetricName.COMPETITION_SCORE))
    registry.register(MetricName.COMPETITION_SCORE, lambda c, d: float("nan"))
    with pytest.raises(MetricEvaluationError, match="non-finite"):
        registry.evaluate(context, definition(MetricName.COMPETITION_SCORE))
