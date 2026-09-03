"""P9.S4.M06 — point-in-time benchmark and factor alpha/beta engine."""

from __future__ import annotations

import math

import numpy as np
import statsmodels.api as sm

from .common import GrossNet, MetricRecord, MetricStatus, Unit, content_sha256
from .factor_models import (
    FactorCoefficient,
    FactorExposurePanel,
    FactorRegressionRecord,
    FactorRegressionRequest,
    FactorRegressionResult,
    RegressionCovariance,
    RegressionDiagnosticReport,
    RollingFactorPanel,
    RollingFactorRecord,
)
from .reason_codes import ReasonCode


def _aligned_rows(request: FactorRegressionRequest, factor_ids: tuple[str, ...], returns: tuple[float, ...]):
    factor_map = {
        observation.timestamp: {value.factor_id: value.value for value in observation.values}
        for observation in request.factors.observations
    }
    risk_free_map = {point.timestamp: point.value for point in request.risk_free.points}
    rows = []
    for timestamp, strategy_return in zip(request.returns.timestamps, returns):
        factors = factor_map.get(timestamp)
        risk_free = risk_free_map.get(timestamp)
        if factors is None or risk_free is None:
            continue
        if any(factor_id not in factors for factor_id in factor_ids):
            continue
        rows.append(
            (
                timestamp,
                strategy_return - risk_free,
                [factors[factor_id] for factor_id in factor_ids],
            )
        )
    return rows


def _fit(rows, model_spec, request, gross_net):
    factor_ids = model_spec.factor_ids
    count = len(rows)
    minimum = max(request.policy.minimum_observations, len(factor_ids) + 2)
    if count < minimum:
        return FactorRegressionRecord(
            factor_model_id=model_spec.factor_model_id,
            factor_model_version=model_spec.factor_model_version,
            gross_net=gross_net,
            status=MetricStatus.INSUFFICIENT_SAMPLE.value,
            observation_count=count,
            coefficients=(),
            r_squared=None,
            residual_volatility_annualized=None,
            condition_number=None,
            covariance_method=request.policy.covariance.value,
            limitations=(ReasonCode.INSUFFICIENT_SAMPLE.value,),
        )
    y = np.asarray([row[1] for row in rows], dtype=np.float64)
    x = np.asarray([row[2] for row in rows], dtype=np.float64)
    x = sm.add_constant(x, has_constant="add")
    condition_number = float(np.linalg.cond(x))
    if not math.isfinite(condition_number) or condition_number > request.policy.condition_number_limit:
        return FactorRegressionRecord(
            factor_model_id=model_spec.factor_model_id,
            factor_model_version=model_spec.factor_model_version,
            gross_net=gross_net,
            status=MetricStatus.INVALID.value,
            observation_count=count,
            coefficients=(),
            r_squared=None,
            residual_volatility_annualized=None,
            condition_number=condition_number if math.isfinite(condition_number) else None,
            covariance_method=request.policy.covariance.value,
            limitations=(ReasonCode.REGRESSION_SINGULAR.value,),
        )
    model = sm.OLS(y, x, hasconst=True)
    if request.policy.covariance is RegressionCovariance.HAC:
        result = model.fit(
            cov_type="HAC",
            cov_kwds={"maxlags": request.policy.hac_max_lags, "kernel": "bartlett"},
            use_t=True,
        )
    elif request.policy.covariance is RegressionCovariance.HC3:
        result = model.fit(cov_type="HC3", use_t=True)
    else:
        result = model.fit(cov_type="nonrobust", use_t=True)
    names = ("alpha",) + factor_ids
    coefficients = []
    for index, name in enumerate(names):
        estimate = float(result.params[index])
        standard_error = float(result.bse[index])
        if name == "alpha":
            estimate *= request.returns.periods_per_year
            standard_error *= request.returns.periods_per_year
            name = "alpha_annualized"
        coefficients.append(
            FactorCoefficient(
                name=name,
                estimate=estimate,
                standard_error=standard_error,
                t_statistic=float(result.tvalues[index]),
                p_value=float(result.pvalues[index]),
            )
        )
    residual_volatility = float(np.std(result.resid, ddof=1)) * math.sqrt(request.returns.periods_per_year)
    return FactorRegressionRecord(
        factor_model_id=model_spec.factor_model_id,
        factor_model_version=model_spec.factor_model_version,
        gross_net=gross_net,
        status=MetricStatus.QUALIFIED.value,
        observation_count=count,
        coefficients=tuple(coefficients),
        r_squared=float(result.rsquared),
        residual_volatility_annualized=residual_volatility,
        condition_number=condition_number,
        covariance_method=request.policy.covariance.value,
    )


def _rolling(request, model, returns, gross_net):
    if request.policy.rolling_window is None:
        return []
    rows = _aligned_rows(request, model.factor_ids, returns)
    window = request.policy.rolling_window
    records = []
    if len(rows) < window:
        return records
    for end in range(window, len(rows) + 1):
        subset = rows[end - window : end]
        fitted = _fit(subset, model, request, gross_net)
        records.append(
            RollingFactorRecord(
                factor_model_id=model.factor_model_id,
                factor_model_version=model.factor_model_version,
                gross_net=gross_net,
                end_timestamp=subset[-1][0],
                observation_count=fitted.observation_count,
                coefficients=fitted.coefficients,
                r_squared=fitted.r_squared,
                status=fitted.status,
            )
        )
    return records


def compute_factor_regressions(request: FactorRegressionRequest) -> FactorRegressionResult:
    """Fit authorized factor models with exact timestamp alignment and robust covariance."""

    identity = request.returns.identity
    regressions = []
    rolling = []
    metrics: list[MetricRecord] = []
    limitations: list[str] = []
    for model_id, version in request.policy.factor_model_ids:
        model = request.registry.get(model_id, version)
        for returns, gross_net in (
            (request.returns.gross_returns, GrossNet.GROSS.value),
            (request.returns.net_returns, GrossNet.NET.value),
        ):
            rows = _aligned_rows(request, model.factor_ids, returns)
            record = _fit(rows, model, request, gross_net)
            regressions.append(record)
            rolling.extend(_rolling(request, model, returns, gross_net))
            if record.status != MetricStatus.QUALIFIED.value:
                limitations.extend(record.limitations)
                continue
            for coefficient in record.coefficients:
                metric_id = f"factor.{model.factor_model_id}.{coefficient.name}"
                metrics.append(
                    MetricRecord(
                        metric_id=metric_id,
                        metric_version=model.factor_model_version,
                        producer_module_id="P9.S4.M06",
                        value=coefficient.estimate,
                        unit=Unit.ANNUALIZED_DECIMAL if coefficient.name == "alpha_annualized" else Unit.COEFFICIENT,
                        status=MetricStatus.QUALIFIED,
                        gross_net=GrossNet(gross_net),
                        sample_count=record.observation_count,
                        method=f"OLS_{record.covariance_method}",
                        annualization_periods=request.returns.periods_per_year if coefficient.name == "alpha_annualized" else None,
                    )
                )
            metrics.extend(
                [
                    MetricRecord(metric_id=f"factor.{model.factor_model_id}.r_squared", metric_version=model.factor_model_version, producer_module_id="P9.S4.M06", value=record.r_squared, unit=Unit.RATIO, status=MetricStatus.QUALIFIED, gross_net=GrossNet(gross_net), sample_count=record.observation_count, method=f"OLS_{record.covariance_method}"),
                    MetricRecord(metric_id=f"factor.{model.factor_model_id}.residual_volatility", metric_version=model.factor_model_version, producer_module_id="P9.S4.M06", value=record.residual_volatility_annualized, unit=Unit.ANNUALIZED_DECIMAL, status=MetricStatus.QUALIFIED, gross_net=GrossNet(gross_net), sample_count=record.observation_count, method=f"OLS_{record.covariance_method}", annualization_periods=request.returns.periods_per_year),
                ]
            )

    exposure_body = {
        "panel_id": f"factor-exposure-{identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": tuple(metrics),
        "diagnostics": (),
        "limitations": tuple(sorted(set(limitations))),
        "regressions": tuple(regressions),
    }
    exposures = FactorExposurePanel(**exposure_body, content_sha256=content_sha256(exposure_body))
    rolling_body = {
        "panel_id": f"rolling-factors-{identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": (),
        "diagnostics": (),
        "limitations": tuple(sorted(set(limitations))),
        "records": tuple(rolling),
    }
    rolling_panel = RollingFactorPanel(**rolling_body, content_sha256=content_sha256(rolling_body))
    diagnostic_body = {
        "panel_id": f"regression-diagnostics-{identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": (),
        "diagnostics": (),
        "limitations": tuple(sorted(set(limitations))),
        "registry_id": request.registry.registry_id,
        "registry_version": request.registry.registry_version,
    }
    diagnostics = RegressionDiagnosticReport(**diagnostic_body, content_sha256=content_sha256(diagnostic_body))
    return FactorRegressionResult(exposures=exposures, rolling=rolling_panel, diagnostics=diagnostics)
