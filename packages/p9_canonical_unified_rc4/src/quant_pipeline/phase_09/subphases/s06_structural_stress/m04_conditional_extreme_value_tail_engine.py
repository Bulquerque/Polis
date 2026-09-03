from __future__ import annotations

import math

import numpy as np
from scipy.stats import genpareto, kstest

from .contracts import CapabilityState, S6State
from .models import ConditionalEVTResult, EVTParameterInterval, EVTRequest
from .numerics import ewma_scales, lag1_autocorrelation
from .randomness import derive_generator


def _fit_excesses(excesses: np.ndarray) -> tuple[float, float]:
    shape, location, scale = genpareto.fit(excesses, floc=0.0)
    if abs(location) > 1e-12 or not math.isfinite(shape) or not math.isfinite(scale) or scale <= 0:
        raise ValueError("invalid GPD fit")
    return float(shape), float(scale)


def _tail_quantile(
    threshold: float,
    shape: float,
    scale: float,
    exceedance_probability: float,
    target_tail_probability: float,
) -> float:
    ratio = target_tail_probability / exceedance_probability
    if not 0 < ratio < 1:
        raise ValueError("target tail probability must be below threshold exceedance probability")
    if abs(shape) < 1e-10:
        return threshold - scale * math.log(ratio)
    return threshold + scale / shape * (ratio ** (-shape) - 1.0)


def _expected_shortfall(threshold: float, quantile: float, shape: float, scale: float) -> float:
    if shape >= 1.0:
        raise ValueError("expected shortfall is infinite for tail index >= 1")
    return (quantile + scale - shape * threshold) / (1.0 - shape)


def _threshold_fit(standardized: np.ndarray, quantile: float) -> tuple[float, float, float, int]:
    threshold = float(np.quantile(standardized, quantile))
    excesses = standardized[standardized > threshold] - threshold
    if excesses.size < 3:
        raise ValueError("too few exceedances")
    shape, scale = _fit_excesses(excesses)
    return threshold, shape, scale, int(excesses.size)


def _bootstrap_intervals(
    excesses: np.ndarray,
    request: EVTRequest,
) -> tuple[EVTParameterInterval, ...]:
    generator = derive_generator(request.seed_policy, request.loss_series_id, "evt-parameters")
    estimates: list[tuple[float, float]] = []
    for _ in range(request.policy.parameter_bootstrap_replicates):
        sampled = generator.choice(excesses, size=excesses.size, replace=True)
        try:
            estimates.append(_fit_excesses(sampled))
        except (ValueError, RuntimeError, FloatingPointError):
            continue
    if len(estimates) < max(20, request.policy.parameter_bootstrap_replicates // 4):
        return ()
    array = np.asarray(estimates, dtype=np.float64)
    alpha = 1.0 - request.policy.confidence_level
    lows = np.quantile(array, alpha / 2.0, axis=0)
    highs = np.quantile(array, 1.0 - alpha / 2.0, axis=0)
    means = np.mean(array, axis=0)
    return (
        EVTParameterInterval(
            parameter="tail_index",
            estimate=float(means[0]),
            low=float(lows[0]),
            high=float(highs[0]),
        ),
        EVTParameterInterval(
            parameter="scale",
            estimate=float(means[1]),
            low=float(lows[1]),
            high=float(highs[1]),
        ),
    )


def fit_conditional_evt(request: EVTRequest) -> ConditionalEVTResult:
    """Fit a POT/GPD tail to volatility-standardized loss innovations."""

    losses = np.asarray(request.losses, dtype=np.float64)
    scales = (
        np.asarray(request.conditional_scales, dtype=np.float64)
        if request.conditional_scales is not None
        else ewma_scales(losses, request.policy.ewma_lambda, request.policy.minimum_scale)
    )
    standardized = losses / scales
    residual_autocorrelation = lag1_autocorrelation(standardized)
    if abs(residual_autocorrelation) > request.policy.maximum_absolute_residual_autocorrelation:
        return ConditionalEVTResult(
            status=S6State.DEPENDENCE_NOT_REMOVED,
            loss_series_id=request.loss_series_id,
            threshold=None,
            exceedance_count=0,
            tail_index=None,
            scale_parameter=None,
            conditional_var=None,
            conditional_expected_shortfall=None,
            residual_lag1_autocorrelation=residual_autocorrelation,
            threshold_tail_index_range=None,
            ks_statistic=None,
            capability_state=CapabilityState.RESEARCH_ONLY,
            reason_codes=("P9_STRESS_EVT_RESIDUAL_DEPENDENCE",),
            limitations=("standardized residuals retain material lag-one dependence",),
        )

    try:
        threshold, shape, scale, exceedance_count = _threshold_fit(
            standardized, request.policy.threshold_quantile
        )
    except (ValueError, RuntimeError, FloatingPointError):
        return ConditionalEVTResult(
            status=S6State.THRESHOLD_NOT_IDENTIFIED,
            loss_series_id=request.loss_series_id,
            threshold=None,
            exceedance_count=0,
            tail_index=None,
            scale_parameter=None,
            conditional_var=None,
            conditional_expected_shortfall=None,
            residual_lag1_autocorrelation=residual_autocorrelation,
            threshold_tail_index_range=None,
            ks_statistic=None,
            capability_state=CapabilityState.UNAVAILABLE,
            reason_codes=("P9_STRESS_EVT_FIT_FAILED",),
        )
    if exceedance_count < request.policy.minimum_exceedances:
        return ConditionalEVTResult(
            status=S6State.INSUFFICIENT_EXCEEDANCES,
            loss_series_id=request.loss_series_id,
            threshold=threshold,
            exceedance_count=exceedance_count,
            tail_index=shape,
            scale_parameter=scale,
            conditional_var=None,
            conditional_expected_shortfall=None,
            residual_lag1_autocorrelation=residual_autocorrelation,
            threshold_tail_index_range=None,
            ks_statistic=None,
            capability_state=CapabilityState.UNAVAILABLE,
            reason_codes=("P9_STRESS_EVT_INSUFFICIENT_EXCEEDANCES",),
        )

    sensitivity_shapes: list[float] = []
    for quantile in (
        request.policy.threshold_quantile - request.policy.threshold_sensitivity_step,
        request.policy.threshold_quantile,
        request.policy.threshold_quantile + request.policy.threshold_sensitivity_step,
    ):
        if not 0.5 < quantile < 1.0:
            continue
        try:
            _, candidate_shape, _, _ = _threshold_fit(standardized, quantile)
            sensitivity_shapes.append(candidate_shape)
        except (ValueError, RuntimeError, FloatingPointError):
            continue
    shape_range = (
        max(sensitivity_shapes) - min(sensitivity_shapes)
        if len(sensitivity_shapes) >= 2
        else float("inf")
    )
    excesses = standardized[standardized > threshold] - threshold
    ks = kstest(excesses, "genpareto", args=(shape, 0.0, scale)).statistic
    target_tail_probability = 1.0 - request.policy.confidence_level
    exceedance_probability = exceedance_count / standardized.size
    try:
        standardized_var = _tail_quantile(
            threshold,
            shape,
            scale,
            exceedance_probability,
            target_tail_probability,
        )
        standardized_es = _expected_shortfall(threshold, standardized_var, shape, scale)
    except ValueError:
        return ConditionalEVTResult(
            status=S6State.UNSTABLE_TAIL_INDEX,
            loss_series_id=request.loss_series_id,
            threshold=threshold,
            exceedance_count=exceedance_count,
            tail_index=shape,
            scale_parameter=scale,
            conditional_var=None,
            conditional_expected_shortfall=None,
            residual_lag1_autocorrelation=residual_autocorrelation,
            threshold_tail_index_range=shape_range if math.isfinite(shape_range) else None,
            ks_statistic=float(ks),
            capability_state=CapabilityState.RESEARCH_ONLY,
            reason_codes=("P9_STRESS_EVT_TAIL_INDEX_INVALID_FOR_ES",),
        )

    current_scale = float(scales[-1])
    intervals = _bootstrap_intervals(excesses, request)
    reason_codes: list[str] = []
    limitations: list[str] = []
    if shape_range > request.policy.maximum_tail_index_range or not intervals:
        reason_codes.append("P9_STRESS_EVT_THRESHOLD_UNSTABLE")
        limitations.append("tail parameters are unstable across thresholds or bootstrap samples")
        status = S6State.QUALIFIED_WITH_LIMITATIONS
        capability = CapabilityState.LIMITED
    else:
        status = S6State.QUALIFIED
        capability = CapabilityState.AVAILABLE
    return ConditionalEVTResult(
        status=status,
        loss_series_id=request.loss_series_id,
        threshold=threshold,
        exceedance_count=exceedance_count,
        tail_index=shape,
        scale_parameter=scale,
        conditional_var=current_scale * standardized_var,
        conditional_expected_shortfall=current_scale * standardized_es,
        residual_lag1_autocorrelation=residual_autocorrelation,
        threshold_tail_index_range=shape_range if math.isfinite(shape_range) else None,
        ks_statistic=float(ks),
        parameter_intervals=intervals,
        capability_state=capability,
        reason_codes=tuple(reason_codes),
        limitations=tuple(limitations),
    )
