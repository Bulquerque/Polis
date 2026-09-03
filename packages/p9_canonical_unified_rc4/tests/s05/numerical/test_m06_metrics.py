from __future__ import annotations

import math

import numpy as np
import pytest

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.contracts import BootstrapMethod, MetricDefinition, MetricName, S5State
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m03_time_series_block_bootstrap_engine import generate_bootstrap_indices
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m06_bootstrap_metric_distribution_builder import build_metric_distributions
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import BlockBootstrapRequest, MetricDistributionRequest
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.policies import BootstrapPolicy


def test_observed_sharpe_matches_manual_oracle(context, series_panel, seed_policy) -> None:
    bootstrap = generate_bootstrap_indices(
        BlockBootstrapRequest(
            context=context,
            observation_count=len(series_panel.timestamps),
            block_length=7,
            seed_policy=seed_policy,
            policy=BootstrapPolicy(method=BootstrapMethod.MOVING, replicate_count=120),
        )
    )
    assert bootstrap.manifest is not None
    definition = MetricDefinition(
        metric_id="net-sharpe",
        metric_name=MetricName.SHARPE,
        target_series_id="strategy",
        metric_version="1.0.0",
        threshold=0.0,
        risk_free_series_id="risk_free",
        minimum_valid_replicates=50,
    )
    result = build_metric_distributions(
        MetricDistributionRequest(
            context=context,
            series=series_panel,
            indices=bootstrap.manifest,
            metric_definitions=(definition,),
        )
    )
    target = np.asarray([row[0] - row[2] for row in series_panel.values])
    expected = target.mean() / target.std(ddof=1) * math.sqrt(252.0)
    assert result.estimates[0].observed_value == pytest.approx(expected)
    assert result.estimates[0].valid_replicates == 120


def test_missing_competition_metric_is_explicit(context, series_panel, seed_policy) -> None:
    bootstrap = generate_bootstrap_indices(
        BlockBootstrapRequest(
            context=context,
            observation_count=len(series_panel.timestamps),
            block_length=5,
            seed_policy=seed_policy,
            policy=BootstrapPolicy(replicate_count=60),
        )
    )
    assert bootstrap.manifest is not None
    definition = MetricDefinition(
        metric_id="competition",
        metric_name=MetricName.COMPETITION_SCORE,
        target_series_id="strategy",
        metric_version="1.0.0",
        minimum_valid_replicates=50,
    )
    result = build_metric_distributions(
        MetricDistributionRequest(
            context=context,
            series=series_panel,
            indices=bootstrap.manifest,
            metric_definitions=(definition,),
        )
    )
    assert result.estimates[0].status is S5State.INSUFFICIENT_EVIDENCE
    assert "P9_BOOTSTRAP_METRIC_UNAVAILABLE" in result.estimates[0].reason_codes
