from __future__ import annotations

import math

import numpy as np
from scipy.stats import kurtosis, norm, skew

from .contracts import S5State
from .models import SharpeInferenceRequest, SharpeInferenceResult
from .numerics import autocorrelation, stable_correlation, to_float_matrix

MODULE_ID = "P9.S5.M07"
EULER_MASCHERONI = 0.5772156649015329


def _target_returns(request: SharpeInferenceRequest) -> np.ndarray:
    try:
        column = request.series.series_ids.index(request.target_series_id)
    except ValueError as error:
        raise ValueError("target_series_id not found in series panel") from error
    matrix = to_float_matrix(request.series.values)
    values = np.asarray(matrix[:, column], dtype=np.float64)
    if request.series.risk_free_series_id is not None:
        risk_free_column = request.series.series_ids.index(request.series.risk_free_series_id)
        values = values - matrix[:, risk_free_column]
    return values


def _sharpe(values: np.ndarray) -> float:
    standard_deviation = float(np.std(values, ddof=1))
    if standard_deviation <= np.finfo(np.float64).eps:
        raise ValueError("Sharpe undefined for zero variance")
    return float(np.mean(values) / standard_deviation)


def _autocorrelation_adjustment(values: np.ndarray, maximum_lag: int) -> float:
    lags = min(maximum_lag, values.size - 1)
    if lags < 1:
        return 1.0
    acf = autocorrelation(values, lags)[1:]
    weights = 1.0 - np.arange(1, lags + 1, dtype=np.float64) / (lags + 1.0)
    long_run_multiplier = 1.0 + 2.0 * float(np.sum(weights * acf))
    return max(long_run_multiplier, np.finfo(np.float64).eps)


def _psr(
    observed_period_sharpe: float,
    benchmark_period_sharpe: float,
    observation_count: int,
    sample_skewness: float,
    pearson_kurtosis: float,
) -> float:
    denominator_term = (
        1.0
        - sample_skewness * observed_period_sharpe
        + ((pearson_kurtosis - 1.0) / 4.0) * observed_period_sharpe**2
    )
    if denominator_term <= np.finfo(np.float64).eps:
        raise ValueError("PSR denominator is not positive")
    statistic = (
        (observed_period_sharpe - benchmark_period_sharpe)
        * math.sqrt(observation_count - 1)
        / math.sqrt(denominator_term)
    )
    return float(norm.cdf(statistic))


def _effective_trial_count(request: SharpeInferenceRequest) -> float:
    matrix = to_float_matrix(request.trial_performance.performance_values)
    n_trials = matrix.shape[1]
    if n_trials == 1:
        eigen_count = 1.0
    else:
        correlation = stable_correlation(matrix)
        eigenvalues = np.clip(np.linalg.eigvalsh(correlation), 0.0, None)
        denominator = float(eigenvalues @ eigenvalues)
        eigen_count = (
            float(eigenvalues.sum() ** 2 / denominator)
            if denominator > np.finfo(np.float64).eps
            else 1.0
        )
    cluster_count = float(
        len(set(request.trial_performance.economic_cluster_ids))
        if request.trial_performance.economic_cluster_ids is not None
        else n_trials
    )
    method = request.policy.effective_trial_method
    if method == "ECONOMIC_CLUSTER_COUNT":
        selected = cluster_count
    elif method == "MINIMUM_OF_BOTH":
        selected = min(eigen_count, cluster_count)
    else:
        selected = eigen_count
    return float(np.clip(selected, 1.0, float(n_trials)))


def _trial_annualized_sharpes(request: SharpeInferenceRequest) -> np.ndarray:
    matrix = to_float_matrix(request.trial_performance.performance_values)
    sharpes: list[float] = []
    for column in range(matrix.shape[1]):
        values = matrix[:, column]
        try:
            sharpes.append(_sharpe(values) * math.sqrt(request.series.periods_per_year))
        except ValueError:
            sharpes.append(0.0)
    return np.asarray(sharpes, dtype=np.float64)


def _expected_max_sharpe(trial_sharpes: np.ndarray, effective_trials: float) -> float:
    if effective_trials <= 1.0 or trial_sharpes.size <= 1:
        return float(np.mean(trial_sharpes))
    standard_deviation = float(np.std(trial_sharpes, ddof=1))
    if standard_deviation <= np.finfo(np.float64).eps:
        return float(np.mean(trial_sharpes))
    n_eff = max(effective_trials, 1.000001)
    expected_standard_max = (
        (1.0 - EULER_MASCHERONI) * norm.ppf(1.0 - 1.0 / n_eff)
        + EULER_MASCHERONI * norm.ppf(1.0 - 1.0 / (n_eff * math.e))
    )
    return float(np.mean(trial_sharpes) + standard_deviation * expected_standard_max)


def infer_sharpe(request: SharpeInferenceRequest) -> SharpeInferenceResult:
    """Compute adjusted Sharpe, PSR, DSR and minimum track record length."""

    try:
        values = _target_returns(request)
    except ValueError:
        return SharpeInferenceResult(
            status=S5State.INVALID_INPUT,
            target_series_id=request.target_series_id,
            target_configuration_id=(request.target_configuration_id or request.context.configuration_id),
            observation_count=1,
            observed_annualized_sharpe=None,
            autocorrelation_adjusted_annualized_sharpe=None,
            probabilistic_sharpe_ratio=None,
            deflated_sharpe_ratio=None,
            benchmark_annualized_sharpe=request.policy.benchmark_annualized_sharpe,
            effective_trial_count=None,
            expected_max_annualized_sharpe=None,
            minimum_track_record_observations=None,
            skewness=None,
            pearson_kurtosis=None,
            reason_codes=("P9_OVERFIT_TARGET_SERIES_MISSING",),
        )
    nobs = values.size
    if nobs < request.policy.minimum_observations:
        return SharpeInferenceResult(
            status=S5State.INSUFFICIENT_HISTORY,
            target_series_id=request.target_series_id,
            target_configuration_id=(request.target_configuration_id or request.context.configuration_id),
            observation_count=max(nobs, 1),
            observed_annualized_sharpe=None,
            autocorrelation_adjusted_annualized_sharpe=None,
            probabilistic_sharpe_ratio=None,
            deflated_sharpe_ratio=None,
            benchmark_annualized_sharpe=request.policy.benchmark_annualized_sharpe,
            effective_trial_count=None,
            expected_max_annualized_sharpe=None,
            minimum_track_record_observations=None,
            skewness=None,
            pearson_kurtosis=None,
            reason_codes=("P9_OVERFIT_PSR_INSUFFICIENT_SAMPLE",),
        )
    try:
        period_sharpe = _sharpe(values)
    except ValueError:
        return SharpeInferenceResult(
            status=S5State.INSUFFICIENT_EVIDENCE,
            target_series_id=request.target_series_id,
            target_configuration_id=(request.target_configuration_id or request.context.configuration_id),
            observation_count=nobs,
            observed_annualized_sharpe=None,
            autocorrelation_adjusted_annualized_sharpe=None,
            probabilistic_sharpe_ratio=None,
            deflated_sharpe_ratio=None,
            benchmark_annualized_sharpe=request.policy.benchmark_annualized_sharpe,
            effective_trial_count=None,
            expected_max_annualized_sharpe=None,
            minimum_track_record_observations=None,
            skewness=None,
            pearson_kurtosis=None,
            reason_codes=("P9_OVERFIT_SHARPE_ZERO_VARIANCE",),
        )
    sample_skewness = float(skew(values, bias=False))
    sample_kurtosis = float(kurtosis(values, fisher=False, bias=False))
    if not np.isfinite(sample_skewness):
        sample_skewness = 0.0
    if not np.isfinite(sample_kurtosis) or sample_kurtosis < 1.0:
        sample_kurtosis = 3.0
    annualization = math.sqrt(request.series.periods_per_year)
    annualized_sharpe = period_sharpe * annualization
    multiplier = _autocorrelation_adjustment(values, request.policy.autocorrelation_lags)
    adjusted_annualized_sharpe = period_sharpe * math.sqrt(
        request.series.periods_per_year / multiplier
    )
    benchmark_period_sharpe = request.policy.benchmark_annualized_sharpe / annualization
    try:
        psr = _psr(
            period_sharpe,
            benchmark_period_sharpe,
            nobs,
            sample_skewness,
            sample_kurtosis,
        )
    except ValueError:
        psr = None
    effective_trials = _effective_trial_count(request)
    trial_sharpes = _trial_annualized_sharpes(request)
    expected_max = _expected_max_sharpe(trial_sharpes, effective_trials)
    try:
        dsr = _psr(
            period_sharpe,
            expected_max / annualization,
            nobs,
            sample_skewness,
            sample_kurtosis,
        )
    except ValueError:
        dsr = None
    difference = period_sharpe - benchmark_period_sharpe
    minimum_track_record: float | None = None
    if difference > 0.0:
        variance_term = (
            1.0
            - sample_skewness * period_sharpe
            + ((sample_kurtosis - 1.0) / 4.0) * period_sharpe**2
        )
        if variance_term > 0.0:
            z_value = float(norm.ppf(request.policy.confidence_level))
            minimum_track_record = 1.0 + variance_term * (z_value / difference) ** 2
    reason_codes: list[str] = []
    limitations: list[str] = []
    status = S5State.SUCCESS
    if not request.trial_performance.family_complete:
        status = S5State.TRIAL_FAMILY_INCOMPLETE
        reason_codes.append("P9_OVERFIT_TRIAL_FAMILY_INCOMPLETE")
        limitations.append(
            "DSR is reported but cannot qualify robustness with an incomplete trial family"
        )
    if dsr is None:
        status = S5State.EFFECTIVE_TRIAL_COUNT_UNRESOLVED
        reason_codes.append("P9_OVERFIT_DSR_NOT_IDENTIFIABLE")
    return SharpeInferenceResult(
        status=status,
        target_series_id=request.target_series_id,
        target_configuration_id=(request.target_configuration_id or request.context.configuration_id),
        observation_count=nobs,
        observed_annualized_sharpe=float(annualized_sharpe),
        autocorrelation_adjusted_annualized_sharpe=float(adjusted_annualized_sharpe),
        probabilistic_sharpe_ratio=psr,
        deflated_sharpe_ratio=dsr,
        benchmark_annualized_sharpe=request.policy.benchmark_annualized_sharpe,
        effective_trial_count=effective_trials,
        expected_max_annualized_sharpe=expected_max,
        minimum_track_record_observations=minimum_track_record,
        skewness=sample_skewness,
        pearson_kurtosis=sample_kurtosis,
        reason_codes=tuple(reason_codes),
        limitations=tuple(limitations),
    )
