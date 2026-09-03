"""P9.S4.M03 — transparent historical and parametric tail-risk engine."""

from __future__ import annotations

import math

import numpy as np
from scipy.stats import norm

from .common import GrossNet, MetricRecord, MetricStatus, Unit, content_sha256, safe_mean, sample_standard_deviation
from .reason_codes import ReasonCode
from .tail_models import (
    ParametricTailModel,
    TailEstimate,
    TailMethodDiagnostics,
    TailRiskMetricPanel,
    TailRiskRequest,
    TailRiskResult,
    VaRBreachPanel,
    VaRBreachRecord,
)


def _historical_estimate(losses: list[float], level: float, method: str):
    value_at_risk = float(np.quantile(np.asarray(losses), level, method=method))
    tail = [loss for loss in losses if loss >= value_at_risk]
    expected_shortfall = safe_mean(tail) if tail else value_at_risk
    return value_at_risk, expected_shortfall


def _normal_estimate(returns: list[float], level: float):
    mean_loss = -safe_mean(returns)
    sigma = sample_standard_deviation(returns)
    z = float(norm.ppf(level))
    value_at_risk = mean_loss + z * sigma
    expected_shortfall = mean_loss + sigma * float(norm.pdf(z)) / (1.0 - level)
    return value_at_risk, expected_shortfall


def _metric(metric_id, value, gross_net, count, method, status=MetricStatus.QUALIFIED, limitations=()):
    return MetricRecord(
        metric_id=metric_id,
        metric_version="1.0.0",
        producer_module_id="P9.S4.M03",
        value=value,
        unit=Unit.DECIMAL_RETURN,
        status=status,
        gross_net=gross_net,
        sample_count=count,
        method=method,
        limitations=limitations,
    )


def compute_tail_risk(request: TailRiskRequest) -> TailRiskResult:
    """Compute positive-loss VaR/ES without mixing historical, parametric, and scenarios."""

    identity = request.returns.identity
    estimates: list[TailEstimate] = []
    breaches: list[VaRBreachRecord] = []
    metrics: list[MetricRecord] = []
    limitations: list[str] = []
    minimum = request.policy.minimum_samples.minimum_tail_observations

    for values, gross_net in (
        (list(request.returns.gross_returns), GrossNet.GROSS),
        (list(request.returns.net_returns), GrossNet.NET),
    ):
        losses = [-value for value in values]
        for level in request.policy.confidence_levels:
            if len(values) < minimum:
                limitation = ReasonCode.TAIL_SAMPLE_INSUFFICIENT.value
                limitations.append(limitation)
                estimates.append(
                    TailEstimate(
                        gross_net=gross_net.value,
                        method="HISTORICAL",
                        confidence_level=level,
                        value_at_risk=None,
                        expected_shortfall=None,
                        breach_count=0,
                        observation_count=len(values),
                        status=MetricStatus.INSUFFICIENT_SAMPLE.value,
                        limitations=(limitation,),
                    )
                )
                metrics.extend(
                    [
                        _metric("tail.var", None, gross_net, len(values), "historical", MetricStatus.INSUFFICIENT_SAMPLE, (limitation,)),
                        _metric("tail.expected_shortfall", None, gross_net, len(values), "historical", MetricStatus.INSUFFICIENT_SAMPLE, (limitation,)),
                    ]
                )
                continue
            historical_var, historical_es = _historical_estimate(
                losses,
                level,
                request.policy.quantile_method.value,
            )
            breach_count = sum(loss > historical_var for loss in losses)
            estimates.append(
                TailEstimate(
                    gross_net=gross_net.value,
                    method="HISTORICAL",
                    confidence_level=level,
                    value_at_risk=historical_var,
                    expected_shortfall=historical_es,
                    breach_count=breach_count,
                    observation_count=len(values),
                    status=MetricStatus.QUALIFIED.value,
                )
            )
            metrics.extend(
                [
                    _metric(f"tail.var.{level:.4f}", historical_var, gross_net, len(values), f"historical_{request.policy.quantile_method.value}"),
                    _metric(f"tail.expected_shortfall.{level:.4f}", historical_es, gross_net, len(values), f"historical_{request.policy.quantile_method.value}"),
                ]
            )
            for timestamp, loss in zip(request.returns.timestamps, losses):
                if loss > historical_var:
                    breaches.append(
                        VaRBreachRecord(
                            timestamp=timestamp,
                            gross_net=gross_net.value,
                            confidence_level=level,
                            method="HISTORICAL",
                            loss=loss,
                            value_at_risk=historical_var,
                        )
                    )
            if request.policy.parametric_model is ParametricTailModel.NORMAL:
                parametric_var, parametric_es = _normal_estimate(values, level)
                estimates.append(
                    TailEstimate(
                        gross_net=gross_net.value,
                        method="NORMAL_PARAMETRIC",
                        confidence_level=level,
                        value_at_risk=parametric_var,
                        expected_shortfall=parametric_es,
                        breach_count=sum(loss > parametric_var for loss in losses),
                        observation_count=len(values),
                        status=MetricStatus.LIMITED.value,
                        limitations=(ReasonCode.PARAMETRIC_ASSUMPTION_LIMITED.value,),
                    )
                )
                metrics.extend(
                    [
                        _metric(f"tail.var_normal.{level:.4f}", parametric_var, gross_net, len(values), "normal_parametric", MetricStatus.LIMITED, (ReasonCode.PARAMETRIC_ASSUMPTION_LIMITED.value,)),
                        _metric(f"tail.expected_shortfall_normal.{level:.4f}", parametric_es, gross_net, len(values), "normal_parametric", MetricStatus.LIMITED, (ReasonCode.PARAMETRIC_ASSUMPTION_LIMITED.value,)),
                    ]
                )
        if values:
            lower = float(np.quantile(np.asarray(values), 0.05, method=request.policy.quantile_method.value))
            upper = float(np.quantile(np.asarray(values), 0.95, method=request.policy.quantile_method.value))
            tail_ratio = upper / abs(lower) if lower < 0 else None
            metrics.append(
                MetricRecord(
                    metric_id="tail.ratio.95_05",
                    metric_version="1.0.0",
                    producer_module_id="P9.S4.M03",
                    value=tail_ratio,
                    unit=Unit.RATIO,
                    status=MetricStatus.QUALIFIED if tail_ratio is not None else MetricStatus.UNDEFINED,
                    gross_net=gross_net,
                    sample_count=len(values),
                    method=f"quantiles_{request.policy.quantile_method.value}",
                )
            )

    scenario_losses = tuple(request.scenarios.records) if request.scenarios is not None else ()
    metric_body = {
        "panel_id": f"tail-{identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": tuple(metrics),
        "diagnostics": (),
        "limitations": tuple(sorted(set(limitations))),
        "estimates": tuple(estimates),
        "scenario_losses": scenario_losses,
    }
    metric_panel = TailRiskMetricPanel(**metric_body, content_sha256=content_sha256(metric_body))
    breach_body = {
        "panel_id": f"breaches-{identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": (),
        "diagnostics": (),
        "limitations": tuple(sorted(set(limitations))),
        "breaches": tuple(breaches),
    }
    breach_panel = VaRBreachPanel(**breach_body, content_sha256=content_sha256(breach_body))
    diagnostic_body = {
        "panel_id": f"tail-diagnostics-{identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": (),
        "diagnostics": (),
        "limitations": tuple(sorted(set(limitations))),
        "quantile_method": request.policy.quantile_method.value,
        "parametric_model": request.policy.parametric_model.value,
    }
    diagnostics = TailMethodDiagnostics(
        **diagnostic_body,
        content_sha256=content_sha256(diagnostic_body),
    )
    return TailRiskResult(metrics=metric_panel, breaches=breach_panel, diagnostics=diagnostics)
