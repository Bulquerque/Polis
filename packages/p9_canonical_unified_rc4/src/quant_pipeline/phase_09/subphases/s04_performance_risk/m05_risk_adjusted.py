"""P9.S4.M05 — risk-adjusted performance metrics and basic Sharpe inference."""

from __future__ import annotations

import math

from scipy.stats import norm

from .base_models import MetricApplicability
from .common import GrossNet, MetricRecord, MetricStatus, Unit, content_sha256, safe_mean, sample_standard_deviation
from .reason_codes import ReasonCode
from .risk_adjusted_models import (
    RiskAdjustedMetricPanel,
    RiskAdjustedRequest,
    RiskAdjustedResult,
    SharpeDiagnosticPanel,
)


def _find_metric(panel, metric_id: str, gross_net: GrossNet):
    for metric in panel.metrics:
        if metric.metric_id == metric_id and metric.gross_net is gross_net:
            return metric.value
    return None


def _autocorrelation_factor(request: RiskAdjustedRequest) -> float | None:
    lags = []
    for record in request.distribution.diagnostics.serial_correlations:
        if record.lag <= request.policy.autocorrelation_max_lag and record.net_autocorrelation is not None:
            lags.append((record.lag, record.net_autocorrelation))
    if not lags:
        return 1.0
    maximum = max(lag for lag, _ in lags)
    factor = 1.0 + 2.0 * math.fsum(
        (1.0 - lag / (maximum + 1.0)) * correlation
        for lag, correlation in lags
    )
    return factor if factor > 0 else None


def _probabilistic_sharpe(values: list[float], benchmark: float):
    if len(values) < 3:
        return None, None, None, None
    standard_deviation = sample_standard_deviation(values)
    if standard_deviation == 0:
        return None, None, None, None
    mean = safe_mean(values)
    sharpe_period = mean / standard_deviation
    skewness = _find_moment(values, 3)
    pearson_kurtosis = _find_moment(values, 4)
    denominator_sq = 1.0 - skewness * sharpe_period + ((pearson_kurtosis - 1.0) / 4.0) * sharpe_period**2
    if denominator_sq <= 0:
        return None, skewness, pearson_kurtosis, None
    z_value = (sharpe_period - benchmark) * math.sqrt(len(values) - 1) / math.sqrt(denominator_sq)
    probability = float(norm.cdf(z_value))
    return probability, skewness, pearson_kurtosis, denominator_sq


def _find_moment(values: list[float], order: int) -> float:
    mean = safe_mean(values)
    standard_deviation = sample_standard_deviation(values)
    standardized = [(value - mean) / standard_deviation for value in values]
    if order == 3:
        return safe_mean([value**3 for value in standardized])
    if order == 4:
        return safe_mean([value**4 for value in standardized])
    raise ValueError("unsupported moment order")


def _metric(metric_id, value, unit, count, method, status=MetricStatus.QUALIFIED, gross_net=GrossNet.NET, periods=None, limitations=()):
    return MetricRecord(
        metric_id=metric_id,
        metric_version="1.0.0",
        producer_module_id="P9.S4.M05",
        value=value,
        unit=unit,
        status=status,
        gross_net=gross_net,
        sample_count=count,
        method=method,
        annualization_periods=periods,
        limitations=limitations,
    )


def compute_risk_adjusted(request: RiskAdjustedRequest) -> RiskAdjustedResult:
    """Compute Sharpe-family, downside, drawdown, and benchmark-relative metrics."""

    returns = list(
        request.returns.return_series.excess_returns
        if request.returns.return_series.excess_returns is not None
        else request.returns.return_series.net_returns
    )
    net_returns = list(request.returns.return_series.net_returns)
    active_returns = list(request.returns.return_series.active_returns or ())
    periods = request.returns.return_series.periods_per_year
    count = len(returns)
    limitations: list[str] = []
    applicability: list[MetricApplicability] = []
    metrics: list[MetricRecord] = []

    if request.returns.return_series.excess_returns is None:
        limitations.append(ReasonCode.RISK_FREE_UNAVAILABLE.value)
    if count < request.policy.minimum_observations:
        limitation = ReasonCode.INSUFFICIENT_TRACK_RECORD.value
        limitations.append(limitation)
        for metric_id in ("ratio.sharpe", "ratio.sharpe_autocorrelation_adjusted", "ratio.psr", "ratio.sortino", "ratio.omega"):
            metrics.append(_metric(metric_id, None, Unit.RATIO if metric_id != "ratio.psr" else Unit.PROBABILITY, count, "insufficient_track_record", MetricStatus.INSUFFICIENT_SAMPLE, limitations=(limitation,)))
            applicability.append(MetricApplicability(metric_id=metric_id, status=MetricStatus.INSUFFICIENT_SAMPLE.value, reason_codes=(limitation,), observation_count=count))
        sharpe_factor = None
        skewness = None
        pearson_kurtosis = None
        mtrl = None
    else:
        standard_deviation = sample_standard_deviation(returns)
        mean = safe_mean(returns)
        if standard_deviation == 0:
            sharpe = None
            limitations.append(ReasonCode.ZERO_RISK_DENOMINATOR.value)
        else:
            sharpe = mean / standard_deviation * math.sqrt(periods)
        sharpe_factor = _autocorrelation_factor(request)
        adjusted_sharpe = sharpe / math.sqrt(sharpe_factor) if sharpe is not None and sharpe_factor is not None else None
        probability, skewness, pearson_kurtosis, denominator_sq = _probabilistic_sharpe(
            returns,
            request.policy.probabilistic_sharpe_benchmark,
        )
        downside = [min(value - request.policy.mar_per_period, 0.0) ** 2 for value in net_returns]
        downside_annualized = math.sqrt(math.fsum(downside) / len(downside)) * math.sqrt(periods) if downside else 0.0
        annualized_mar_excess = (safe_mean(net_returns) - request.policy.mar_per_period) * periods if net_returns else None
        sortino = annualized_mar_excess / downside_annualized if annualized_mar_excess is not None and downside_annualized > 0 else None
        gains = math.fsum(max(value - request.policy.omega_threshold_per_period, 0.0) for value in net_returns)
        losses = math.fsum(max(request.policy.omega_threshold_per_period - value, 0.0) for value in net_returns)
        omega = gains / losses if losses > 0 else None
        metrics.extend(
            [
                _metric("ratio.sharpe", sharpe, Unit.RATIO, count, "mean_excess_over_sample_std", MetricStatus.QUALIFIED if sharpe is not None else MetricStatus.UNDEFINED, periods=periods),
                _metric("ratio.sharpe_autocorrelation_adjusted", adjusted_sharpe, Unit.RATIO, count, "lo_long_run_variance_adjustment", MetricStatus.QUALIFIED if adjusted_sharpe is not None else MetricStatus.UNDEFINED, periods=periods),
                _metric("ratio.psr", probability, Unit.PROBABILITY, count, "probabilistic_sharpe_non_normal", MetricStatus.QUALIFIED if probability is not None else MetricStatus.UNDEFINED),
                _metric("ratio.sortino", sortino, Unit.RATIO, count, "annualized_mar_excess_over_downside_deviation", MetricStatus.QUALIFIED if sortino is not None else MetricStatus.UNDEFINED, periods=periods),
                _metric("ratio.omega", omega, Unit.RATIO, count, "gain_loss_integral_empirical", MetricStatus.QUALIFIED if omega is not None else MetricStatus.UNDEFINED),
            ]
        )
        for metric in metrics:
            applicability.append(MetricApplicability(metric_id=metric.metric_id, status=metric.status.value, reason_codes=metric.limitations, observation_count=count))
        if probability is not None and denominator_sq is not None:
            difference = (safe_mean(returns) / standard_deviation) - request.policy.probabilistic_sharpe_benchmark
            z_required = float(norm.ppf(request.policy.psr_confidence_level))
            mtrl = 1.0 + denominator_sq * (z_required / difference) ** 2 if difference > 0 else None
        else:
            mtrl = None

    net_cagr = _find_metric(request.returns.return_metrics, "return.cagr", GrossNet.NET)
    maximum_drawdown = _find_metric(request.drawdown, "drawdown.maximum", GrossNet.NET)
    calmar = net_cagr / maximum_drawdown if net_cagr is not None and maximum_drawdown not in (None, 0.0) else None
    metrics.append(_metric("ratio.calmar", calmar, Unit.RATIO, len(net_returns), "net_cagr_over_max_drawdown", MetricStatus.QUALIFIED if calmar is not None else MetricStatus.UNDEFINED))
    applicability.append(MetricApplicability(metric_id="ratio.calmar", status=MetricStatus.QUALIFIED.value if calmar is not None else MetricStatus.UNDEFINED.value, observation_count=len(net_returns)))

    if active_returns and len(active_returns) >= request.policy.minimum_observations:
        tracking_error = sample_standard_deviation(active_returns) * math.sqrt(periods)
        information = safe_mean(active_returns) * periods / tracking_error if tracking_error > 0 else None
        metrics.extend(
            [
                _metric("risk.tracking_error", tracking_error, Unit.ANNUALIZED_DECIMAL, len(active_returns), "sample_std_active", periods=periods, gross_net=GrossNet.ACTIVE),
                _metric("ratio.information", information, Unit.RATIO, len(active_returns), "annualized_active_mean_over_tracking_error", MetricStatus.QUALIFIED if information is not None else MetricStatus.UNDEFINED, gross_net=GrossNet.ACTIVE),
            ]
        )
    else:
        limitations.append(ReasonCode.BENCHMARK_UNAVAILABLE.value)
        metrics.append(_metric("ratio.information", None, Unit.RATIO, len(active_returns), "benchmark_unavailable", MetricStatus.UNAVAILABLE, gross_net=GrossNet.ACTIVE, limitations=(ReasonCode.BENCHMARK_UNAVAILABLE.value,)))

    identity = request.returns.return_series.identity
    metric_body = {
        "panel_id": f"risk-adjusted-{identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": tuple(metrics),
        "diagnostics": (),
        "limitations": tuple(sorted(set(limitations))),
        "applicability": tuple(applicability),
    }
    metric_panel = RiskAdjustedMetricPanel(**metric_body, content_sha256=content_sha256(metric_body))
    diagnostic_body = {
        "panel_id": f"sharpe-diagnostics-{identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": (),
        "diagnostics": (),
        "limitations": tuple(sorted(set(limitations))),
        "autocorrelation_adjustment_factor": sharpe_factor,
        "skewness": skewness,
        "pearson_kurtosis": pearson_kurtosis,
        "minimum_track_record_length": mtrl,
    }
    diagnostics = SharpeDiagnosticPanel(**diagnostic_body, content_sha256=content_sha256(diagnostic_body))
    return RiskAdjustedResult(metrics=metric_panel, sharpe_diagnostics=diagnostics)
