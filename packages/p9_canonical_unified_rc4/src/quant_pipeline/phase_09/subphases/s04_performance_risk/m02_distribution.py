"""P9.S4.M02 — volatility, distribution, and serial-dependence engine."""

from __future__ import annotations

import math
import warnings

import numpy as np
from scipy.stats import kurtosis, skew
from statsmodels.stats.diagnostic import acorr_ljungbox

from .common import (
    DiagnosticRecord,
    GrossNet,
    MetricRecord,
    MetricStatus,
    Unit,
    content_sha256,
    sample_standard_deviation,
)
from .distribution_models import (
    DistributionDiagnosticPanel,
    DistributionEngineRequest,
    DistributionEngineResult,
    RollingDistributionRecord,
    SerialCorrelationRecord,
    SerialDependenceReport,
    VolatilityMetricPanel,
)
from .reason_codes import ReasonCode


def _metric(metric_id, value, gross_net, count, method, periods, status=MetricStatus.QUALIFIED, limitations=()):
    return MetricRecord(
        metric_id=metric_id,
        metric_version="1.0.0",
        producer_module_id="P9.S4.M02",
        value=value,
        unit=Unit.ANNUALIZED_DECIMAL if "volatility" in metric_id or "deviation" in metric_id else Unit.COEFFICIENT,
        status=status,
        gross_net=gross_net,
        sample_count=count,
        method=method,
        annualization_periods=periods if "volatility" in metric_id or "deviation" in metric_id else None,
        limitations=limitations,
    )


def _autocorrelation(values: list[float], lag: int) -> float | None:
    if len(values) <= lag:
        return None
    left = np.asarray(values[:-lag], dtype=np.float64)
    right = np.asarray(values[lag:], dtype=np.float64)
    if float(np.std(left)) == 0.0 or float(np.std(right)) == 0.0:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def _moments(values: list[float]) -> tuple[float | None, float | None]:
    if len(values) < 3 or sample_standard_deviation(values) == 0.0:
        return None, None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return (
            float(skew(values, bias=False, nan_policy="raise")),
            float(kurtosis(values, fisher=True, bias=False, nan_policy="raise")),
        )


def _downside_deviation(values: list[float], threshold: float, periods: float) -> float:
    downside = [min(value - threshold, 0.0) ** 2 for value in values]
    return math.sqrt(math.fsum(downside) / len(values)) * math.sqrt(periods)


def _rolling_records(values_gross, values_net, windows, periods):
    records: list[RollingDistributionRecord] = []
    for window in windows:
        if len(values_net) < window:
            continue
        for end in range(window, len(values_net) + 1):
            gross_slice = values_gross[end - window : end]
            net_slice = values_net[end - window : end]
            net_skew, net_kurtosis = _moments(net_slice)
            records.append(
                RollingDistributionRecord(
                    window=window,
                    ending_index=end - 1,
                    net_volatility_annualized=sample_standard_deviation(net_slice) * math.sqrt(periods),
                    gross_volatility_annualized=sample_standard_deviation(gross_slice) * math.sqrt(periods),
                    net_skewness=net_skew,
                    net_excess_kurtosis=net_kurtosis,
                )
            )
    return tuple(records)


def _ljung_box(values: list[float], requested_lag: int):
    if len(values) < 5 or sample_standard_deviation(values) == 0.0:
        return None, None, None
    lag = min(requested_lag, max(1, len(values) // 5))
    result = acorr_ljungbox(np.asarray(values), lags=[lag], return_df=True)
    return lag, float(result["lb_stat"].iloc[-1]), float(result["lb_pvalue"].iloc[-1])


def compute_distribution(request: DistributionEngineRequest) -> DistributionEngineResult:
    """Compute annualized dispersion, sample shape, and serial-dependence diagnostics."""

    gross = list(request.returns.gross_returns)
    net = list(request.returns.net_returns)
    periods = request.returns.periods_per_year
    minimum = request.policy.minimum_samples.minimum_return_observations
    identity = request.returns.identity
    limitations: list[str] = []
    metrics: list[MetricRecord] = []

    for values, gross_net in ((gross, GrossNet.GROSS), (net, GrossNet.NET)):
        count = len(values)
        if count < minimum:
            limitations.append(ReasonCode.INSUFFICIENT_SAMPLE.value)
            for metric_id in (
                "risk.volatility",
                "risk.downside_deviation",
                "risk.upside_deviation",
                "distribution.skewness",
                "distribution.excess_kurtosis",
            ):
                metrics.append(
                    _metric(
                        metric_id,
                        None,
                        gross_net,
                        count,
                        "insufficient_sample",
                        periods,
                        MetricStatus.INSUFFICIENT_SAMPLE,
                        (ReasonCode.INSUFFICIENT_SAMPLE.value,),
                    )
                )
            continue
        standard_deviation = sample_standard_deviation(values)
        skewness, excess_kurtosis = _moments(values)
        upside = [max(value - request.policy.downside_threshold_per_period, 0.0) ** 2 for value in values]
        upside_deviation = math.sqrt(math.fsum(upside) / len(values)) * math.sqrt(periods)
        metrics.extend(
            [
                _metric("risk.volatility", standard_deviation * math.sqrt(periods), gross_net, count, "sample_std_ddof_1", periods),
                _metric("risk.downside_deviation", _downside_deviation(values, request.policy.downside_threshold_per_period, periods), gross_net, count, "lower_partial_moment_order_2", periods),
                _metric("risk.upside_deviation", upside_deviation, gross_net, count, "upper_partial_moment_order_2", periods),
                _metric("distribution.skewness", skewness, gross_net, count, "scipy_skew_bias_false", periods, MetricStatus.QUALIFIED if skewness is not None else MetricStatus.UNDEFINED),
                _metric("distribution.excess_kurtosis", excess_kurtosis, gross_net, count, "scipy_kurtosis_fisher_bias_false", periods, MetricStatus.QUALIFIED if excess_kurtosis is not None else MetricStatus.UNDEFINED),
            ]
        )

    serial_records = tuple(
        SerialCorrelationRecord(
            lag=lag,
            gross_autocorrelation=_autocorrelation(gross, lag),
            net_autocorrelation=_autocorrelation(net, lag),
        )
        for lag in request.policy.autocorrelation_lags
    )
    rolling = _rolling_records(gross, net, request.policy.rolling_windows, periods)
    gross_lag, gross_stat, gross_p = _ljung_box(gross, request.policy.ljung_box_max_lag)
    net_lag, net_stat, net_p = _ljung_box(net, request.policy.ljung_box_max_lag)
    lag = gross_lag or net_lag

    vol_body = {
        "panel_id": f"volatility-{identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": tuple(metrics),
        "diagnostics": (),
        "limitations": tuple(sorted(set(limitations))),
        "periods_per_year": periods,
        "downside_threshold_per_period": request.policy.downside_threshold_per_period,
    }
    volatility = VolatilityMetricPanel(**vol_body, content_sha256=content_sha256(vol_body))

    diag_body = {
        "panel_id": f"distribution-{identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": (),
        "diagnostics": (
            DiagnosticRecord(
                code="P9_S4_M02_ROLLING_RECORD_COUNT",
                message="rolling distribution record count",
                severity="INFO",
                observed=str(len(rolling)),
                expected=">=0",
            ),
        ),
        "limitations": tuple(sorted(set(limitations))),
        "serial_correlations": serial_records,
        "rolling": rolling,
    }
    diagnostics = DistributionDiagnosticPanel(**diag_body, content_sha256=content_sha256(diag_body))

    serial_body = {
        "panel_id": f"serial-{identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": (),
        "diagnostics": (),
        "limitations": tuple(sorted(set(limitations))),
        "ljung_box_lag": lag,
        "gross_ljung_box_statistic": gross_stat,
        "gross_ljung_box_pvalue": gross_p,
        "net_ljung_box_statistic": net_stat,
        "net_ljung_box_pvalue": net_p,
    }
    serial = SerialDependenceReport(**serial_body, content_sha256=content_sha256(serial_body))
    return DistributionEngineResult(
        volatility=volatility,
        diagnostics=diagnostics,
        serial_dependence=serial,
    )
