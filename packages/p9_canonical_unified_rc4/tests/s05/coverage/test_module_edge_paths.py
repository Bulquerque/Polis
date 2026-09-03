from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.contracts import (
    BootstrapMethod,
    ConfidenceIntervalMethod,
    FoldScore,
    FoldScorePanel,
    GrossNet,
    MetricDefinition,
    MetricName,
    S5State,
    TimeSeriesPanel,
    TradeEpisodePanel,
    TrialPerformancePanel,
    TrialState,
)
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m03_time_series_block_bootstrap_engine import generate_bootstrap_indices
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m04_hierarchical_portfolio_bootstrap_engine import evaluate_hierarchical_bootstrap
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m05_trade_and_execution_resampling_engine import resample_trade_episodes
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m06_bootstrap_metric_distribution_builder import _summarize_distribution, build_metric_distributions
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m07_sharpe_inference_and_deflation_engine import (
    _autocorrelation_adjustment,
    _effective_trial_count,
    _expected_max_sharpe,
    _psr,
    infer_sharpe,
)
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m08_backtest_overfitting_multiple_testing_qualification_gate import qualify_backtest
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import (
    BlockBootstrapRequest,
    HierarchicalBootstrapRequest,
    MetricDistributionRequest,
    MetricDistributionResult,
    MetricEstimate,
    RobustnessQualificationRequest,
    SharpeInferenceRequest,
    SharpeInferenceResult,
    TradeResamplingRequest,
)
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.policies import (
    BootstrapPolicy,
    HierarchicalBootstrapPolicy,
    MetricDistributionPolicy,
    MultipleTestingPolicy,
    QualificationThresholdPolicy,
    SharpeInferencePolicy,
    TradeResamplingPolicy,
)


def bootstrap_manifest(context, seed_policy, nobs: int, replicates: int = 20):
    result = generate_bootstrap_indices(BlockBootstrapRequest(
        context=context, observation_count=nobs, block_length=min(5, nobs), seed_policy=seed_policy,
        policy=BootstrapPolicy(method=BootstrapMethod.STATIONARY, replicate_count=replicates),
    ))
    assert result.manifest is not None
    return result.manifest


def test_hierarchical_invalid_single_series_and_warning_paths(context, series_panel, seed_policy) -> None:
    mismatched = bootstrap_manifest(context, seed_policy, len(series_panel.timestamps) - 1)
    invalid = evaluate_hierarchical_bootstrap(HierarchicalBootstrapRequest(context=context, series=series_panel, indices=mismatched))
    assert invalid.status is S5State.INVALID_INPUT

    single = TimeSeriesPanel(
        panel_id="single", timestamps=series_panel.timestamps, series_ids=("strategy",),
        values=tuple((row[0],) for row in series_panel.values), periods_per_year=252.0,
        gross_or_net=GrossNet.NET,
    )
    manifest = bootstrap_manifest(context, seed_policy, len(single.timestamps))
    result = evaluate_hierarchical_bootstrap(HierarchicalBootstrapRequest(
        context=context, series=single, indices=manifest,
        policy=HierarchicalBootstrapPolicy(covariance_distance_warning=0.0, record_replicate_diagnostics=5),
    ))
    assert result.status is S5State.QUALIFIED_WITH_LIMITATIONS
    assert result.minimum_regime_coverage is None
    assert "P9_BOOTSTRAP_COVARIANCE_PRESERVATION_WEAK" in result.reason_codes


def test_hierarchical_low_regime_coverage_and_trade_limits(context, series_panel, trade_panel, seed_policy) -> None:
    manifest = bootstrap_manifest(context, seed_policy, len(series_panel.timestamps), 15)
    result = evaluate_hierarchical_bootstrap(HierarchicalBootstrapRequest(
        context=context, series=series_panel, indices=manifest,
        policy=HierarchicalBootstrapPolicy(minimum_regime_coverage=1.0, record_replicate_diagnostics=15),
    ))
    assert result.status in {S5State.SUCCESS, S5State.QUALIFIED_WITH_LIMITATIONS}

    few = TradeEpisodePanel(panel_id="few", episodes=trade_panel.episodes[:2])
    insufficient = resample_trade_episodes(TradeResamplingRequest(
        context=context, trades=few, seed_policy=seed_policy,
        policy=TradeResamplingPolicy(minimum_trade_count=3, replicate_count=5),
    ))
    assert insufficient.status is S5State.INSUFFICIENT_TRADES

    concentrated = trade_panel.model_copy(update={
        "episodes": tuple(
            episode.model_copy(update={"net_pnl": 10000.0 if i == 0 else 0.01, "total_cost": 1000.0 if i == 0 else 0.01})
            for i, episode in enumerate(trade_panel.episodes)
        )
    })
    warning = resample_trade_episodes(TradeResamplingRequest(
        context=context, trades=concentrated, seed_policy=seed_policy,
        policy=TradeResamplingPolicy(replicate_count=5, concentration_warning_hhi=0.2),
    ))
    assert warning.status is S5State.QUALIFIED_WITH_LIMITATIONS
    assert set(warning.reason_codes) == {"P9_BOOTSTRAP_TRADE_PNL_CONCENTRATED", "P9_BOOTSTRAP_TRADE_COST_CONCENTRATED"}


def test_metric_distribution_version_empty_basic_and_summary_paths(context, series_panel, seed_policy) -> None:
    manifest = bootstrap_manifest(context, seed_policy, len(series_panel.timestamps), 12)
    mismatch = MetricDefinition(metric_id="m", metric_name=MetricName.SHARPE, target_series_id="strategy", metric_version="2.0.0")
    result = build_metric_distributions(MetricDistributionRequest(context=context, series=series_panel, indices=manifest, metric_definitions=(mismatch,)))
    assert result.status is S5State.METRIC_VERSION_MISMATCH

    empty = build_metric_distributions(MetricDistributionRequest(context=context, series=series_panel, indices=manifest, metric_definitions=()))
    assert empty.status is S5State.INVALID_INPUT

    definition = MetricDefinition(metric_id="m", metric_name=MetricName.ANNUALIZED_RETURN, target_series_id="strategy", minimum_valid_replicates=2, threshold=0.0)
    request = MetricDistributionRequest(
        context=context, series=series_panel, indices=manifest, metric_definitions=(definition,),
        policy=MetricDistributionPolicy(interval_method=ConfidenceIntervalMethod.BASIC, confidence_level=0.8),
    )
    basic = build_metric_distributions(request)
    assert basic.estimates[0].status is S5State.SUCCESS
    assert basic.estimates[0].probability_above_threshold is not None

    insufficient = _summarize_distribution(np.asarray([np.nan, 1.0]), 1.0, definition.model_copy(update={"minimum_valid_replicates": 2}), request)
    assert insufficient.status is S5State.INSUFFICIENT_VALID_REPLICATES
    partial = _summarize_distribution(
        np.asarray([1.0, 2.0, np.nan]), 1.5,
        definition.model_copy(update={"minimum_valid_replicates": 2}),
        request.model_copy(update={"policy": MetricDistributionPolicy(invalid_replicate_limit=0.1)}),
    )
    assert partial.status is S5State.PARTIAL_METRIC_COVERAGE


def short_panel(series_panel, nobs: int, constant: bool = False) -> TimeSeriesPanel:
    values = series_panel.values[:nobs]
    if constant:
        values = tuple((0.01, 0.005, 0.0) for _ in range(nobs))
    return TimeSeriesPanel(
        panel_id=f"short-{nobs}", timestamps=series_panel.timestamps[:nobs], series_ids=series_panel.series_ids,
        values=values, periods_per_year=series_panel.periods_per_year, gross_or_net=series_panel.gross_or_net,
        benchmark_series_id=series_panel.benchmark_series_id, risk_free_series_id=series_panel.risk_free_series_id,
        metric_registry_version=series_panel.metric_registry_version,
    )


def test_sharpe_edge_paths_and_effective_trial_policies(context, series_panel, trial_panel) -> None:
    empty_metrics = MetricDistributionResult(status=S5State.SUCCESS, metric_registry_version="1.0.0", estimates=())
    missing = infer_sharpe(SharpeInferenceRequest(context=context, series=series_panel, target_series_id="missing", trial_performance=trial_panel, metric_distributions=empty_metrics))
    assert missing.status is S5State.INVALID_INPUT

    insufficient = infer_sharpe(SharpeInferenceRequest(
        context=context, series=short_panel(series_panel, 10), target_series_id="strategy",
        trial_performance=trial_panel.model_copy(update={"timestamps": trial_panel.timestamps[:10], "performance_values": trial_panel.performance_values[:10]}),
        metric_distributions=empty_metrics,
    ))
    assert insufficient.status is S5State.INSUFFICIENT_HISTORY

    zero = infer_sharpe(SharpeInferenceRequest(
        context=context, series=short_panel(series_panel, 40, constant=True), target_series_id="strategy",
        trial_performance=trial_panel.model_copy(update={"timestamps": trial_panel.timestamps[:40], "performance_values": trial_panel.performance_values[:40]}),
        metric_distributions=empty_metrics,
    ))
    assert zero.status is S5State.INSUFFICIENT_EVIDENCE

    incomplete = infer_sharpe(SharpeInferenceRequest(
        context=context, series=series_panel, target_series_id="strategy",
        trial_performance=trial_panel.model_copy(update={"family_complete": False}), metric_distributions=empty_metrics,
    ))
    assert incomplete.status is S5State.TRIAL_FAMILY_INCOMPLETE

    for method in ("ECONOMIC_CLUSTER_COUNT", "MINIMUM_OF_BOTH", "EIGEN_PARTICIPATION_RATIO"):
        request = SharpeInferenceRequest(
            context=context, series=series_panel, target_series_id="strategy", trial_performance=trial_panel,
            metric_distributions=empty_metrics, policy=SharpeInferencePolicy(effective_trial_method=method),
        )
        assert 1.0 <= _effective_trial_count(request) <= len(trial_panel.trial_ids)
    assert _autocorrelation_adjustment(np.asarray([0.1]), 20) == 1.0
    assert _expected_max_sharpe(np.asarray([1.0]), 1.0) == 1.0
    assert _expected_max_sharpe(np.asarray([1.0, 1.0]), 2.0) == 1.0
    with pytest.raises(ValueError):
        _psr(100.0, 0.0, 10, 100.0, 1.0)


def metric_result(probability: float | None = 0.99, lower: float | None = 0.5) -> MetricDistributionResult:
    return MetricDistributionResult(
        status=S5State.SUCCESS, metric_registry_version="1.0.0",
        estimates=(MetricEstimate(
            metric_id="target", metric_name=MetricName.SHARPE, observed_value=1.0,
            bootstrap_mean=1.0, bootstrap_median=1.0, standard_error=0.1,
            confidence_interval_low=lower, confidence_interval_high=1.5,
            lower_confidence_bound=lower, worst_quantile=0.2,
            probability_above_threshold=probability, valid_replicates=100, invalid_replicates=0,
            status=S5State.SUCCESS,
        ),),
    )


def sharpe_result(dsr: float | None = 0.99) -> SharpeInferenceResult:
    return SharpeInferenceResult(
        status=S5State.SUCCESS, target_series_id="strategy", observation_count=100,
        observed_annualized_sharpe=1.0, autocorrelation_adjusted_annualized_sharpe=0.9,
        probabilistic_sharpe_ratio=0.99, deflated_sharpe_ratio=dsr,
        benchmark_annualized_sharpe=0.0, effective_trial_count=2.0,
        expected_max_annualized_sharpe=0.5, minimum_track_record_observations=30.0,
        skewness=0.0, pearson_kurtosis=3.0,
    )


def simple_trials(series_panel, trial_count: int = 2, family_complete: bool = True) -> TrialPerformancePanel:
    n = 80
    x = np.linspace(-0.01, 0.02, n)
    columns = [x + i * 0.0002 for i in range(trial_count)]
    matrix = np.column_stack(columns)
    return TrialPerformancePanel(
        panel_id="simple", timestamps=series_panel.timestamps[:n],
        trial_ids=tuple(f"t{i}" for i in range(trial_count)),
        configuration_ids=tuple("configuration-001" if i == 0 else f"c{i}" for i in range(trial_count)),
        states=tuple(TrialState.COMPLETED for _ in range(trial_count)),
        performance_values=tuple(tuple(float(v) for v in row) for row in matrix),
        family_complete=family_complete,
    )


def qualification_request(context, series_panel, seed_policy, **updates) -> RobustnessQualificationRequest:
    base = dict(
        context=context, target_configuration_id="configuration-001", target_metric_id="target",
        trial_performance=simple_trials(series_panel),
        fold_scores=FoldScorePanel(configuration_id="configuration-001", scores=(FoldScore(fold_id="f", score=1.0, observation_count=40),)),
        metric_distributions=metric_result(), sharpe_inference=sharpe_result(), seed_policy=seed_policy,
        multiple_testing_policy=MultipleTestingPolicy(reality_check_replicates=20),
        threshold_policy=QualificationThresholdPolicy(
            minimum_dsr=0.0, maximum_pbo=1.0, minimum_bootstrap_probability_above_threshold=0.0,
            minimum_worst_fold_score=-100.0, maximum_reality_check_pvalue=1.0, minimum_rank_stability=0.0,
        ),
    )
    base.update(updates)
    return RobustnessQualificationRequest(**base)


def test_qualification_missing_robust_fragile_and_unresolved_paths(context, series_panel, seed_policy) -> None:
    missing = qualify_backtest(qualification_request(
        context, series_panel, seed_policy,
        target_metric_id="absent", metric_distributions=MetricDistributionResult(status=S5State.SUCCESS, metric_registry_version="1.0.0", estimates=()),
    ))
    assert missing.status is S5State.INVALID

    robust = qualify_backtest(qualification_request(context, series_panel, seed_policy))
    assert robust.status is S5State.ROBUST

    fragile = qualify_backtest(qualification_request(
        context, series_panel, seed_policy,
        fold_scores=FoldScorePanel(configuration_id="configuration-001", scores=(FoldScore(fold_id="f", score=-1.0, observation_count=40),)),
        threshold_policy=QualificationThresholdPolicy(
            minimum_dsr=0.0, maximum_pbo=1.0, minimum_bootstrap_probability_above_threshold=0.9,
            minimum_worst_fold_score=0.0, maximum_reality_check_pvalue=1.0, minimum_rank_stability=0.0,
        ),
        metric_distributions=metric_result(probability=0.1),
    ))
    assert fragile.status is S5State.FRAGILE
    assert "P9_OVERFIT_WORST_FOLD_FAILURE" in fragile.reason_codes

    one_trial = simple_trials(series_panel, trial_count=1, family_complete=False)
    unresolved = qualify_backtest(qualification_request(
        context, series_panel, seed_policy, trial_performance=one_trial,
        sharpe_inference=sharpe_result(dsr=None), metric_distributions=metric_result(probability=None),
    ))
    assert unresolved.status is S5State.SELECTION_BIAS_UNRESOLVED
    assert unresolved.pbo.applicable is False
    assert unresolved.multiple_testing.applicable is False


def test_cscv_sampling_branch_is_deterministic(context, series_panel, seed_policy) -> None:
    policy = MultipleTestingPolicy(cscv_slices=8, maximum_cscv_combinations=2, reality_check_replicates=10)
    request = qualification_request(context, series_panel, seed_policy, multiple_testing_policy=policy)
    first = qualify_backtest(request)
    second = qualify_backtest(request)
    assert first == second
    assert first.pbo.combination_count == 2

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m01_dependence_and_sampling_diagnostics import diagnose_dependence
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m02_automatic_block_length_selector import _optimal_block_length, select_block_length
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m07_sharpe_inference_and_deflation_engine import _trial_annualized_sharpes
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import BlockLengthSelectionRequest, DependenceDiagnosticsRequest
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.policies import BlockLengthPolicy
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.runner import S5PipelineError, run_s5
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import S5RunRequest


def test_block_length_constant_fallback_and_median(context, series_panel) -> None:
    assert _optimal_block_length(np.ones(20)) == (1.0, 1.0)
    constant = TimeSeriesPanel(
        panel_id="constant", timestamps=series_panel.timestamps[:60], series_ids=("strategy", "benchmark"),
        values=tuple((0.01, 0.02) for _ in range(60)), periods_per_year=252.0, gross_or_net=GrossNet.NET,
    )
    diagnostics = diagnose_dependence(DependenceDiagnosticsRequest(context=context, series=constant))
    # Force a real dependence horizon so the transparent fallback branch is exercised.
    forced = diagnostics.model_copy(update={
        "series_diagnostics": tuple(item.model_copy(update={"dependence_horizon": 4}) for item in diagnostics.series_diagnostics)
    })
    result = select_block_length(BlockLengthSelectionRequest(
        context=context, series=constant, diagnostics=forced,
        policy=BlockLengthPolicy(joint_aggregation="MEDIAN", fallback_dependence_multiplier=2.0),
    ))
    assert result.status is S5State.QUALIFIED_WITH_LIMITATIONS
    assert all(item.used_fallback for item in result.estimates)
    assert result.joint_stationary_block_length == 8


def test_trial_sharpes_zero_variance_branch(context, series_panel, trial_panel) -> None:
    constant_matrix = tuple(tuple(0.01 for _ in trial_panel.trial_ids) for _ in trial_panel.timestamps)
    request = SharpeInferenceRequest(
        context=context, series=series_panel, target_series_id="strategy",
        trial_performance=trial_panel.model_copy(update={"performance_values": constant_matrix}),
        metric_distributions=MetricDistributionResult(status=S5State.SUCCESS, metric_registry_version="1.0.0", estimates=()),
    )
    assert np.array_equal(_trial_annualized_sharpes(request), np.zeros(len(trial_panel.trial_ids)))


def make_run_request(context, series_panel, trade_panel, trial_panel, fold_scores, seed_policy, metric_definitions, method, include_trades=True):
    return S5RunRequest(
        dependence=DependenceDiagnosticsRequest(context=context, series=series_panel, trades=trade_panel if include_trades else None),
        bootstrap_policy=BootstrapPolicy(method=method, replicate_count=30),
        seed_policy=seed_policy,
        trade_policy=TradeResamplingPolicy(replicate_count=30),
        metric_definitions=metric_definitions,
        sharpe_target_series_id="strategy",
        trial_performance=trial_panel,
        fold_scores=fold_scores,
        target_metric_id="net-sharpe",
    )


def test_runner_moving_circular_and_missing_trades(context, series_panel, trade_panel, trial_panel, fold_scores, seed_policy, metric_definitions) -> None:
    for method in (BootstrapMethod.MOVING, BootstrapMethod.CIRCULAR):
        bundle = run_s5(make_run_request(context, series_panel, trade_panel, trial_panel, fold_scores, seed_policy, metric_definitions, method))
        assert bundle.bootstrap.manifest is not None
        assert bundle.bootstrap.manifest.method is method
    without_trades = run_s5(make_run_request(context, series_panel, trade_panel, trial_panel, fold_scores, seed_policy, metric_definitions, BootstrapMethod.STATIONARY, include_trades=False))
    assert without_trades.trade_resampling is None
    m05 = next(receipt for receipt in without_trades.module_receipts if receipt.module_id == "P9.S5.M05")
    assert m05.status is S5State.INSUFFICIENT_EVIDENCE


def test_runner_blocks_irregular_time(context, series_panel, trial_panel, fold_scores, seed_policy, metric_definitions) -> None:
    timestamps = list(series_panel.timestamps)
    timestamps[10] = timestamps[9] + timedelta(hours=12)
    timestamps[11:] = [item - timedelta(hours=12) for item in timestamps[11:]]
    irregular = series_panel.model_copy(update={"timestamps": tuple(timestamps)})
    request = make_run_request(context, irregular, None, trial_panel, fold_scores, seed_policy, metric_definitions, BootstrapMethod.STATIONARY, include_trades=False)
    with pytest.raises(S5PipelineError, match="M01 blocked"):
        run_s5(request)
