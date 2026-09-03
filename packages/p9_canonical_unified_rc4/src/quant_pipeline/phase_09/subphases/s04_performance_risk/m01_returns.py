"""P9.S4.M01 — return and wealth-path engine."""

from __future__ import annotations

import math
from datetime import timedelta
from decimal import Decimal

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.integrity_models import CashCategory

from .base_models import AnnualizationPolicy
from .common import (
    DiagnosticRecord,
    GrossNet,
    MetricRecord,
    MetricStatus,
    ReturnConvention,
    Unit,
    content_sha256,
    safe_mean,
)
from .reason_codes import ReasonCode
from .return_models import (
    ReturnEngineRequest,
    ReturnEngineResult,
    ReturnMetricPanel,
    ReturnSeriesPanel,
    WealthPathPanel,
    WealthPoint,
)

_SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60


def _periods_per_year(timestamps: list, policy: AnnualizationPolicy) -> float:
    if policy.periods_per_year is not None:
        return policy.periods_per_year
    if len(timestamps) < 2:
        raise ValueError(ReasonCode.IRREGULAR_FREQUENCY_UNRESOLVED.value)
    gaps = [
        (right - left).total_seconds()
        for left, right in zip(timestamps, timestamps[1:])
    ]
    sorted_gaps = sorted(gaps)
    median = sorted_gaps[len(sorted_gaps) // 2]
    if median <= 0:
        raise ValueError(ReasonCode.IRREGULAR_FREQUENCY_UNRESOLVED.value)
    tolerance = policy.regularity_tolerance_fraction
    if any(abs(gap - median) / median > tolerance for gap in gaps):
        raise ValueError(ReasonCode.IRREGULAR_FREQUENCY_UNRESOLVED.value)
    return _SECONDS_PER_YEAR / median


def _aligned_value(series, timestamp):
    if series is None:
        return None
    values = {point.timestamp: point.value for point in series.points}
    return values.get(timestamp)


def _return_value(current: Decimal, previous: Decimal, flow: Decimal, convention: ReturnConvention) -> float:
    if previous == 0:
        raise ValueError("previous wealth cannot be zero")
    simple = float((current - flow) / previous - Decimal("1"))
    if convention is ReturnConvention.SIMPLE:
        return simple
    if simple <= -1:
        raise ValueError("log return undefined for total loss or worse")
    return math.log1p(simple)


def _compound(values: list[float], convention: ReturnConvention) -> float:
    if not values:
        return 0.0
    if convention is ReturnConvention.LOG:
        return math.expm1(math.fsum(values))
    wealth = 1.0
    for value in values:
        wealth *= 1.0 + value
    return wealth - 1.0


def _metric(
    metric_id: str,
    value: float | None,
    unit: Unit,
    gross_net: GrossNet,
    sample_count: int,
    method: str,
    periods: float | None = None,
    status: MetricStatus = MetricStatus.QUALIFIED,
    limitations: tuple[str, ...] = (),
) -> MetricRecord:
    return MetricRecord(
        metric_id=metric_id,
        metric_version="1.0.0",
        producer_module_id="P9.S4.M01",
        value=value,
        unit=unit,
        status=status,
        gross_net=gross_net,
        sample_count=sample_count,
        method=method,
        annualization_periods=periods,
        limitations=limitations,
    )


def compute_returns(request: ReturnEngineRequest) -> ReturnEngineResult:
    """Derive one reconciled wealth path and all baseline return series."""

    handoff = request.qualified_backtest.handoff
    valuations = list(handoff.valuations)
    timestamps = [record.valuation_time for record in valuations]
    periods = _periods_per_year(timestamps, request.policy.annualization)

    external_categories = {CashCategory.DEPOSIT, CashCategory.WITHDRAWAL}
    cumulative_cost = Decimal("0")
    previous_cost = Decimal("0")
    points: list[WealthPoint] = []
    gross_returns: list[float] = []
    net_returns: list[float] = []
    active_returns: list[float] = []
    excess_returns: list[float] = []
    benchmark_complete = request.benchmark is not None
    risk_free_complete = request.risk_free is not None

    for index, valuation in enumerate(valuations):
        period_start = valuations[index - 1].valuation_time if index else None
        external_flow = sum(
            (
                entry.amount
                for entry in handoff.cash_entries
                if entry.category in external_categories
                and entry.event_time <= valuation.valuation_time
                and (period_start is None or entry.event_time > period_start)
            ),
            Decimal("0"),
        )
        period_cost = valuation.costs - previous_cost
        if period_cost < 0:
            raise ValueError("valuation costs must be cumulative and non-decreasing")
        previous_cost = valuation.costs
        cumulative_cost = valuation.costs
        gross_wealth = valuation.nav + cumulative_cost
        benchmark_return = None
        risk_free_return = None
        gross_return = None
        net_return = None
        active_return = None
        excess_return = None
        if index:
            previous = points[-1]
            net_return = _return_value(
                valuation.nav,
                previous.net_wealth,
                external_flow,
                request.policy.convention,
            )
            gross_return = _return_value(
                gross_wealth,
                previous.gross_wealth,
                external_flow,
                request.policy.convention,
            )
            benchmark_return = _aligned_value(request.benchmark, valuation.valuation_time)
            risk_free_return = _aligned_value(request.risk_free, valuation.valuation_time)
            if benchmark_return is None:
                benchmark_complete = False
            else:
                active_return = net_return - benchmark_return
                active_returns.append(active_return)
            if risk_free_return is None:
                risk_free_complete = False
            else:
                excess_return = net_return - risk_free_return
                excess_returns.append(excess_return)
            net_returns.append(net_return)
            gross_returns.append(gross_return)
        points.append(
            WealthPoint(
                timestamp=valuation.valuation_time,
                nav=valuation.nav,
                gross_wealth=gross_wealth,
                net_wealth=valuation.nav,
                external_flow=external_flow,
                period_cost=period_cost,
                cumulative_cost=cumulative_cost,
                gross_return=gross_return,
                net_return=net_return,
                benchmark_return=benchmark_return,
                risk_free_return=risk_free_return,
                active_return=active_return,
                excess_return=excess_return,
            )
        )

    return_timestamps = tuple(timestamps[1:])
    gross_cumulative = _compound(gross_returns, request.policy.convention)
    net_cumulative = _compound(net_returns, request.policy.convention)
    gross_growth = max(0.0, 1.0 + gross_cumulative)
    net_growth = max(0.0, 1.0 + net_cumulative)
    years = len(net_returns) / periods if net_returns else 0.0
    gross_cagr = gross_growth ** (1.0 / years) - 1.0 if years > 0 and gross_growth > 0 else None
    net_cagr = net_growth ** (1.0 / years) - 1.0 if years > 0 and net_growth > 0 else None
    geometric_net = (net_growth ** (1.0 / len(net_returns)) - 1.0) if net_returns and net_growth > 0 else None
    geometric_gross = (gross_growth ** (1.0 / len(gross_returns)) - 1.0) if gross_returns and gross_growth > 0 else None

    metrics = [
        _metric("return.cumulative", gross_cumulative, Unit.DECIMAL_RETURN, GrossNet.GROSS, len(gross_returns), "compound"),
        _metric("return.cumulative", net_cumulative, Unit.DECIMAL_RETURN, GrossNet.NET, len(net_returns), "compound"),
        _metric("return.cagr", gross_cagr, Unit.ANNUALIZED_DECIMAL, GrossNet.GROSS, len(gross_returns), "compound_annual_growth", periods, MetricStatus.QUALIFIED if gross_cagr is not None else MetricStatus.UNDEFINED),
        _metric("return.cagr", net_cagr, Unit.ANNUALIZED_DECIMAL, GrossNet.NET, len(net_returns), "compound_annual_growth", periods, MetricStatus.QUALIFIED if net_cagr is not None else MetricStatus.UNDEFINED),
        _metric("return.arithmetic_mean", safe_mean(gross_returns) if gross_returns else None, Unit.DECIMAL_RETURN, GrossNet.GROSS, len(gross_returns), "arithmetic_mean", status=MetricStatus.QUALIFIED if gross_returns else MetricStatus.INSUFFICIENT_SAMPLE),
        _metric("return.arithmetic_mean", safe_mean(net_returns) if net_returns else None, Unit.DECIMAL_RETURN, GrossNet.NET, len(net_returns), "arithmetic_mean", status=MetricStatus.QUALIFIED if net_returns else MetricStatus.INSUFFICIENT_SAMPLE),
        _metric("return.geometric_mean", geometric_gross, Unit.DECIMAL_RETURN, GrossNet.GROSS, len(gross_returns), "geometric_mean", status=MetricStatus.QUALIFIED if geometric_gross is not None else MetricStatus.UNDEFINED),
        _metric("return.geometric_mean", geometric_net, Unit.DECIMAL_RETURN, GrossNet.NET, len(net_returns), "geometric_mean", status=MetricStatus.QUALIFIED if geometric_net is not None else MetricStatus.UNDEFINED),
    ]
    limitations: list[str] = []
    if request.benchmark is not None and not benchmark_complete:
        limitations.append(ReasonCode.BENCHMARK_UNAVAILABLE.value)
    if request.risk_free is not None and not risk_free_complete:
        limitations.append(ReasonCode.RISK_FREE_UNAVAILABLE.value)

    identity = request.qualified_backtest.identity()
    panel_body = {
        "panel_id": f"wealth-{handoff.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": (),
        "diagnostics": (),
        "limitations": tuple(limitations),
        "points": tuple(points),
        "return_convention": request.policy.convention,
        "periods_per_year": periods,
    }
    wealth_path = WealthPathPanel(**panel_body, content_sha256=content_sha256(panel_body))

    series_body = {
        "panel_id": f"returns-{handoff.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": (),
        "diagnostics": (),
        "limitations": tuple(limitations),
        "timestamps": return_timestamps,
        "gross_returns": tuple(gross_returns),
        "net_returns": tuple(net_returns),
        "active_returns": tuple(active_returns) if benchmark_complete and request.benchmark is not None else None,
        "excess_returns": tuple(excess_returns) if risk_free_complete and request.risk_free is not None else None,
        "periods_per_year": periods,
    }
    return_series = ReturnSeriesPanel(**series_body, content_sha256=content_sha256(series_body))

    metric_body = {
        "panel_id": f"return-metrics-{handoff.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": tuple(metrics),
        "diagnostics": tuple(
            [
                DiagnosticRecord(
                    code="P9_S4_M01_RETURN_COUNT",
                    message="number of calculated return observations",
                    severity="INFO",
                    observed=str(len(net_returns)),
                    expected=">=1 for performance metrics",
                )
            ]
        ),
        "limitations": tuple(limitations),
        "start_nav": valuations[0].nav,
        "end_nav": valuations[-1].nav,
        "total_external_flow": sum((point.external_flow for point in points), Decimal("0")),
        "total_cost": valuations[-1].costs,
    }
    return_metrics = ReturnMetricPanel(**metric_body, content_sha256=content_sha256(metric_body))
    reconciliation_sha = content_sha256(
        {
            "wealth": wealth_path.content_sha256,
            "series": return_series.content_sha256,
            "metrics": return_metrics.content_sha256,
        }
    )
    return ReturnEngineResult(
        wealth_path=wealth_path,
        return_series=return_series,
        return_metrics=return_metrics,
        reconciliation_sha256=reconciliation_sha,
    )
