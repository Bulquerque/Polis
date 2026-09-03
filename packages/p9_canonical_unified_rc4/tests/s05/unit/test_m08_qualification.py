from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.contracts import (
    FoldScore,
    FoldScorePanel,
    S5State,
    TrialPerformancePanel,
    TrialState,
)
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m08_backtest_overfitting_multiple_testing_qualification_gate import qualify_backtest
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import (
    MetricDistributionResult,
    MetricEstimate,
    RobustnessQualificationRequest,
    SharpeInferenceResult,
)
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.contracts import MetricName


def _overfit_trials() -> TrialPerformancePanel:
    slices = 8
    observations_per_slice = 20
    trial_count = 4
    matrix = np.full((slices * observations_per_slice, trial_count), -0.01)
    for slice_index in range(slices):
        winner = slice_index % trial_count
        start = slice_index * observations_per_slice
        matrix[start : start + observations_per_slice, winner] = 0.03
    start_time = datetime(2024, 1, 1, tzinfo=UTC)
    return TrialPerformancePanel(
        panel_id="overfit",
        timestamps=tuple(start_time + timedelta(days=i) for i in range(matrix.shape[0])),
        trial_ids=("t0", "t1", "t2", "t3"),
        configuration_ids=("configuration-001", "c1", "c2", "c3"),
        states=tuple(TrialState.COMPLETED for _ in range(trial_count)),
        performance_values=tuple(tuple(float(v) for v in row) for row in matrix),
        family_complete=True,
        economic_cluster_ids=("a", "b", "c", "d"),
    )


def _metric_result() -> MetricDistributionResult:
    return MetricDistributionResult(
        status=S5State.SUCCESS,
        metric_registry_version="1.0.0",
        estimates=(
            MetricEstimate(
                metric_id="net-sharpe",
                metric_name=MetricName.SHARPE,
                observed_value=1.5,
                bootstrap_mean=1.0,
                bootstrap_median=1.0,
                standard_error=0.2,
                confidence_interval_low=0.6,
                confidence_interval_high=1.4,
                lower_confidence_bound=0.6,
                worst_quantile=0.5,
                probability_above_threshold=0.95,
                valid_replicates=1000,
                invalid_replicates=0,
                status=S5State.SUCCESS,
            ),
        ),
    )


def _sharpe_result() -> SharpeInferenceResult:
    return SharpeInferenceResult(
        status=S5State.SUCCESS,
        target_series_id="strategy",
        observation_count=160,
        observed_annualized_sharpe=1.5,
        autocorrelation_adjusted_annualized_sharpe=1.3,
        probabilistic_sharpe_ratio=0.99,
        deflated_sharpe_ratio=0.99,
        benchmark_annualized_sharpe=0.0,
        effective_trial_count=4.0,
        expected_max_annualized_sharpe=0.8,
        minimum_track_record_observations=80.0,
        skewness=0.0,
        pearson_kurtosis=3.0,
    )


def test_overfit_trial_family_is_not_qualified(context, seed_policy) -> None:
    request = RobustnessQualificationRequest(
        context=context,
        target_configuration_id="configuration-001",
        target_metric_id="net-sharpe",
        trial_performance=_overfit_trials(),
        fold_scores=FoldScorePanel(
            configuration_id="configuration-001",
            scores=(
                FoldScore(fold_id="f0", score=0.2, observation_count=40),
                FoldScore(fold_id="f1", score=0.2, observation_count=40),
            ),
        ),
        metric_distributions=_metric_result(),
        sharpe_inference=_sharpe_result(),
        seed_policy=seed_policy,
    )
    result = qualify_backtest(request)
    assert result.status in {S5State.BACKTEST_OVERFIT_RISK, S5State.FRAGILE}
    assert result.pbo.applicable
    assert result.pbo.pbo is not None


def test_fold_cohort_mismatch_is_invalid(context, seed_policy) -> None:
    request = RobustnessQualificationRequest(
        context=context,
        target_configuration_id="configuration-001",
        target_metric_id="net-sharpe",
        trial_performance=_overfit_trials(),
        fold_scores=FoldScorePanel(
            configuration_id="different",
            scores=(FoldScore(fold_id="f0", score=1.0, observation_count=40),),
        ),
        metric_distributions=_metric_result(),
        sharpe_inference=_sharpe_result(),
        seed_policy=seed_policy,
    )
    result = qualify_backtest(request)
    assert result.status is S5State.INVALID
    assert "P9_OVERFIT_COHORT_MISMATCH" in result.reason_codes
