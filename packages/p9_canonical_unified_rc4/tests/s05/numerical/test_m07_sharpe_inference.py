from __future__ import annotations

import numpy as np

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.contracts import BootstrapMethod, S5State
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m03_time_series_block_bootstrap_engine import generate_bootstrap_indices
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m06_bootstrap_metric_distribution_builder import build_metric_distributions
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m07_sharpe_inference_and_deflation_engine import infer_sharpe
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import BlockBootstrapRequest, MetricDistributionRequest, SharpeInferenceRequest
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.policies import BootstrapPolicy


def test_autocorrelation_adjustment_reduces_sharpe_and_effective_trials(
    context, series_panel, trial_panel, seed_policy, metric_definitions
) -> None:
    bootstrap = generate_bootstrap_indices(
        BlockBootstrapRequest(
            context=context,
            observation_count=len(series_panel.timestamps),
            block_length=7,
            seed_policy=seed_policy,
            policy=BootstrapPolicy(method=BootstrapMethod.STATIONARY, replicate_count=120),
        )
    )
    assert bootstrap.manifest is not None
    metrics = build_metric_distributions(
        MetricDistributionRequest(
            context=context,
            series=series_panel,
            indices=bootstrap.manifest,
            metric_definitions=metric_definitions,
        )
    )
    result = infer_sharpe(
        SharpeInferenceRequest(
            context=context,
            series=series_panel,
            target_series_id="strategy",
            trial_performance=trial_panel,
            metric_distributions=metrics,
        )
    )
    assert result.status is S5State.SUCCESS
    assert result.observed_annualized_sharpe is not None
    assert result.autocorrelation_adjusted_annualized_sharpe is not None
    assert result.autocorrelation_adjusted_annualized_sharpe < result.observed_annualized_sharpe
    assert result.effective_trial_count is not None
    assert 1.0 <= result.effective_trial_count <= len(trial_panel.trial_ids)
    assert result.probabilistic_sharpe_ratio is not None
    assert result.deflated_sharpe_ratio is not None


def test_identical_trials_have_effective_count_near_one(
    context, series_panel, trial_panel, seed_policy, metric_definitions
) -> None:
    matrix = np.asarray(trial_panel.performance_values)
    repeated = np.tile(matrix[:, [0]], (1, 4))
    duplicate_panel = trial_panel.model_copy(
        update={
            "trial_ids": ("a", "b", "c", "d"),
            "configuration_ids": ("a", "b", "c", "d"),
            "states": trial_panel.states[:4],
            "performance_values": tuple(tuple(float(v) for v in row) for row in repeated),
            "economic_cluster_ids": ("same", "same", "same", "same"),
        }
    )
    bootstrap = generate_bootstrap_indices(
        BlockBootstrapRequest(
            context=context,
            observation_count=len(series_panel.timestamps),
            block_length=5,
            seed_policy=seed_policy,
            policy=BootstrapPolicy(replicate_count=100),
        )
    )
    assert bootstrap.manifest is not None
    metrics = build_metric_distributions(
        MetricDistributionRequest(
            context=context,
            series=series_panel,
            indices=bootstrap.manifest,
            metric_definitions=metric_definitions,
        )
    )
    result = infer_sharpe(
        SharpeInferenceRequest(
            context=context,
            series=series_panel,
            target_series_id="strategy",
            trial_performance=duplicate_panel,
            metric_distributions=metrics,
        )
    )
    assert result.effective_trial_count is not None
    assert result.effective_trial_count < 1.1
