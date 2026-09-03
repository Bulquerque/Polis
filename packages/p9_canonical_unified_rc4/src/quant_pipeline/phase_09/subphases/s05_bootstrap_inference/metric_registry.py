from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .contracts import MetricDefinition, MetricName
from .numerics import FloatArray, maximum_drawdown


class MetricEvaluationError(ValueError):
    """Raised when a metric is mathematically undefined for a replicate."""


@dataclass(frozen=True, slots=True)
class MetricContext:
    returns: FloatArray
    periods_per_year: float
    benchmark: FloatArray | None = None
    risk_free: FloatArray | None = None


MetricCalculator = Callable[[MetricContext, MetricDefinition], float]


def _excess_returns(context: MetricContext) -> FloatArray:
    if context.risk_free is None:
        return context.returns
    return context.returns - context.risk_free


def annualized_return(context: MetricContext, _: MetricDefinition) -> float:
    return float(np.mean(context.returns) * context.periods_per_year)


def volatility(context: MetricContext, _: MetricDefinition) -> float:
    if context.returns.size < 2:
        raise MetricEvaluationError("volatility requires at least two observations")
    return float(np.std(context.returns, ddof=1) * np.sqrt(context.periods_per_year))


def sharpe(context: MetricContext, _: MetricDefinition) -> float:
    excess = _excess_returns(context)
    if excess.size < 2:
        raise MetricEvaluationError("Sharpe requires at least two observations")
    standard_deviation = float(np.std(excess, ddof=1))
    if standard_deviation <= np.finfo(np.float64).eps:
        raise MetricEvaluationError("Sharpe undefined for zero variance")
    return float(np.mean(excess) / standard_deviation * np.sqrt(context.periods_per_year))


def cumulative_return(context: MetricContext, _: MetricDefinition) -> float:
    return float(np.prod(1.0 + context.returns) - 1.0)


def cagr(context: MetricContext, _: MetricDefinition) -> float:
    terminal_wealth = float(np.prod(1.0 + context.returns))
    if terminal_wealth <= 0.0:
        raise MetricEvaluationError("CAGR undefined for non-positive terminal wealth")
    years = context.returns.size / context.periods_per_year
    if years <= 0.0:
        raise MetricEvaluationError("CAGR requires a positive horizon")
    return float(terminal_wealth ** (1.0 / years) - 1.0)


def max_drawdown(context: MetricContext, _: MetricDefinition) -> float:
    return maximum_drawdown(context.returns)


def sortino(context: MetricContext, _: MetricDefinition) -> float:
    excess = _excess_returns(context)
    downside = np.minimum(excess, 0.0)
    downside_deviation = float(np.sqrt(np.mean(downside * downside)))
    if downside_deviation <= np.finfo(np.float64).eps:
        raise MetricEvaluationError("Sortino undefined without downside variation")
    return float(np.mean(excess) / downside_deviation * np.sqrt(context.periods_per_year))


def calmar(context: MetricContext, definition: MetricDefinition) -> float:
    growth = cagr(context, definition)
    drawdown = abs(max_drawdown(context, definition))
    if drawdown <= np.finfo(np.float64).eps:
        raise MetricEvaluationError("Calmar undefined without drawdown")
    return float(growth / drawdown)


def expected_shortfall(context: MetricContext, definition: MetricDefinition) -> float:
    losses = -context.returns
    quantile = float(np.quantile(losses, 1.0 - definition.tail_probability))
    tail = losses[losses >= quantile]
    if tail.size == 0:
        raise MetricEvaluationError("Expected Shortfall tail is empty")
    return float(np.mean(tail))


def beta(context: MetricContext, _: MetricDefinition) -> float:
    if context.benchmark is None:
        raise MetricEvaluationError("beta requires a benchmark")
    benchmark_variance = float(np.var(context.benchmark, ddof=1))
    if benchmark_variance <= np.finfo(np.float64).eps:
        raise MetricEvaluationError("beta undefined for zero benchmark variance")
    covariance = float(np.cov(context.returns, context.benchmark, ddof=1)[0, 1])
    return covariance / benchmark_variance


def alpha(context: MetricContext, definition: MetricDefinition) -> float:
    if context.benchmark is None:
        raise MetricEvaluationError("alpha requires a benchmark")
    estimated_beta = beta(context, definition)
    residual = context.returns - estimated_beta * context.benchmark
    return float(np.mean(residual) * context.periods_per_year)


def information_ratio(context: MetricContext, _: MetricDefinition) -> float:
    if context.benchmark is None:
        raise MetricEvaluationError("Information Ratio requires a benchmark")
    active = context.returns - context.benchmark
    tracking_error = float(np.std(active, ddof=1))
    if tracking_error <= np.finfo(np.float64).eps:
        raise MetricEvaluationError("Information Ratio undefined for zero tracking error")
    return float(np.mean(active) / tracking_error * np.sqrt(context.periods_per_year))


class MetricCalculatorRegistry:
    """Versioned calculator registry; upstream analytics may inject its frozen competition metric."""

    def __init__(self) -> None:
        self._calculators: dict[MetricName, MetricCalculator] = {
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

    def register(self, metric_name: MetricName, calculator: MetricCalculator) -> None:
        if metric_name in self._calculators:
            raise ValueError(f"metric calculator already registered: {metric_name}")
        self._calculators[metric_name] = calculator

    def evaluate(self, context: MetricContext, definition: MetricDefinition) -> float:
        calculator = self._calculators.get(definition.metric_name)
        if calculator is None:
            raise MetricEvaluationError(
                f"no calculator registered for {definition.metric_name}; "
                "the upstream implementation reference is required"
            )
        value = float(calculator(context, definition))
        if not np.isfinite(value):
            raise MetricEvaluationError("metric calculator returned a non-finite value")
        return value
