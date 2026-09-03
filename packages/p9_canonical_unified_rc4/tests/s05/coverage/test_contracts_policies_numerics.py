from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import numpy as np
import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.contracts import (
    BootstrapMethod,
    FoldScore,
    FoldScorePanel,
    GrossNet,
    MetricDefinition,
    MetricName,
    ModuleReceipt,
    RunContext,
    S5State,
    TimeSeriesPanel,
    TradeEpisode,
    TradeEpisodePanel,
    TrialPerformancePanel,
    TrialState,
    canonical_json,
    content_sha256,
    ensure_finite_array,
    utc_datetime,
)
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import BootstrapIndexManifest
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.numerics import (
    autocorrelation,
    autocovariance,
    dependence_horizon,
    effective_sample_size,
    hhi,
    ljung_box,
    maximum_drawdown,
    off_diagonal_absolute_mean,
    stable_correlation,
    to_float_matrix,
)
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.policies import (
    BlockLengthPolicy,
    DependencePolicy,
    MetricDistributionPolicy,
    MultipleTestingPolicy,
    SharpeInferencePolicy,
)

HASH = "0" * 64


def test_utc_normalization_hash_and_nonfinite_guard() -> None:
    local = datetime(2025, 1, 1, 3, tzinfo=timezone(timedelta(hours=3)))
    assert utc_datetime(local) == datetime(2025, 1, 1, tzinfo=UTC)
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    assert content_sha256({"a": 1}) == content_sha256({"a": 1})
    ensure_finite_array(((1.0, 2.0),), name="x")
    with pytest.raises(ValueError, match="non-finite"):
        ensure_finite_array((1.0, float("nan")), name="x")


def test_context_and_panel_cross_field_validators(context, series_panel) -> None:
    with pytest.raises(ValidationError, match="available_at"):
        RunContext(**{**context.model_dump(), "available_at": context.decision_time + timedelta(seconds=1)})
    with pytest.raises(ValidationError, match="at least two"):
        TimeSeriesPanel(
            panel_id="p",
            timestamps=(series_panel.timestamps[0],),
            series_ids=("a",),
            values=((0.1,),),
            periods_per_year=252.0,
            gross_or_net=GrossNet.NET,
        )
    base = series_panel.model_dump(mode="python")
    invalid_variants = [
        {**base, "series_ids": ("strategy", "strategy", "risk_free")},
        {**base, "values": base["values"][:-1]},
        {**base, "values": tuple((row[0],) for row in base["values"])},
        {**base, "timestamps": (base["timestamps"][1], base["timestamps"][0], *base["timestamps"][2:])},
        {**base, "fold_ids": ("f",)},
        {**base, "regime_ids": ("r",)},
        {**base, "benchmark_series_id": "missing"},
    ]
    for payload in invalid_variants:
        with pytest.raises(ValidationError):
            TimeSeriesPanel.model_validate(payload)


def test_trade_trial_fold_metric_and_manifest_validators(context, series_panel) -> None:
    at = datetime(2025, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError, match="closed_at"):
        TradeEpisode(
            trade_id="t", candidate_id="c", opened_at=at, closed_at=at - timedelta(days=1),
            instrument_ids=("i",), gross_pnl=1.0, net_pnl=1.0, total_cost=0.0,
        )
    with pytest.raises(ValidationError, match="instrument_ids"):
        TradeEpisode(
            trade_id="t", candidate_id="c", opened_at=at, closed_at=at,
            instrument_ids=(), gross_pnl=1.0, net_pnl=1.0, total_cost=0.0,
        )
    episode = TradeEpisode(
        trade_id="t", candidate_id="c", opened_at=at, closed_at=at,
        instrument_ids=("i",), gross_pnl=1.0, net_pnl=1.0, total_cost=0.0,
    )
    with pytest.raises(ValidationError, match="trade_ids"):
        TradeEpisodePanel(panel_id="p", episodes=(episode, episode))
    trial_base = dict(
        panel_id="p", timestamps=series_panel.timestamps[:2], trial_ids=("t",),
        configuration_ids=("c",), states=(TrialState.COMPLETED,),
        performance_values=((0.1,), (0.2,)), family_complete=True,
    )
    TrialPerformancePanel(**trial_base)
    for update in [
        {"trial_ids": ()},
        {"trial_ids": ("t", "t"), "configuration_ids": ("c", "d"), "states": (TrialState.COMPLETED, TrialState.COMPLETED), "performance_values": ((0.1, 0.2), (0.2, 0.3))},
        {"configuration_ids": ()},
        {"economic_cluster_ids": ("a", "b")},
        {"performance_values": ((0.1,),)},
        {"performance_values": ((0.1, 0.2), (0.2, 0.3))},
    ]:
        with pytest.raises(ValidationError):
            TrialPerformancePanel(**{**trial_base, **update})
    with pytest.raises(ValidationError, match="fold_ids"):
        FoldScorePanel(configuration_id="c", scores=(FoldScore(fold_id="f", score=1.0, observation_count=1), FoldScore(fold_id="f", score=2.0, observation_count=1)))
    with pytest.raises(ValidationError):
        MetricDefinition(metric_id="m", metric_name=MetricName.SHARPE, target_series_id="s", confidence_level=1.0)
    with pytest.raises(ValidationError):
        MetricDefinition(metric_id="m", metric_name=MetricName.SHARPE, target_series_id="s", tail_probability=0.5)
    with pytest.raises(ValidationError):
        BootstrapIndexManifest(
            manifest_id="m", method=BootstrapMethod.MOVING, observation_count=2,
            replicate_count=1, block_length=1, seed_lineage="s", indices=((0,),),
            replicate_sha256=(HASH,), manifest_sha256=HASH,
        )
    with pytest.raises(ValidationError, match="completed_at"):
        ModuleReceipt(module_id="m", status=S5State.SUCCESS, output_sha256=HASH, started_at=at, completed_at=at - timedelta(seconds=1))


def test_policy_validators() -> None:
    invalid = [
        lambda: DependencePolicy(significance_level=0.0),
        lambda: DependencePolicy(maximum_lag=5, portmanteau_lags=(10,)),
        lambda: BlockLengthPolicy(maximum_fraction=0.6),
        lambda: BlockLengthPolicy(joint_aggregation="MEAN"),
        lambda: MetricDistributionPolicy(confidence_level=1.0),
        lambda: MetricDistributionPolicy(worst_quantile=0.5),
        lambda: SharpeInferencePolicy(effective_trial_method="UNKNOWN"),
        lambda: MultipleTestingPolicy(cscv_slices=5),
        lambda: MultipleTestingPolicy(significance_level=0.0),
    ]
    for constructor in invalid:
        with pytest.raises(ValidationError):
            constructor()


def test_numerical_helpers_cover_edge_cases() -> None:
    values = np.asarray([1.0, 2.0, 3.0], dtype=np.float64)
    assert to_float_matrix(((1.0,), (2.0,))).shape == (2, 1)
    with pytest.raises(ValueError):
        to_float_matrix(((1.0, float("nan")),))
    assert autocovariance(values, 0) >= 0
    with pytest.raises(ValueError):
        autocovariance(values, 3)
    constant = np.ones(4, dtype=np.float64)
    assert np.array_equal(autocorrelation(constant, 3), np.asarray([1.0, 0.0, 0.0, 0.0]))
    assert ljung_box(values[:1], 10) == (0.0, 1.0)
    assert 1.0 <= effective_sample_size(values, 2) <= 3.0
    assert dependence_horizon(values[:1], 3) == 1
    assert stable_correlation(np.column_stack([values, np.ones(3)])).shape == (2, 2)
    assert np.array_equal(stable_correlation(values[:, None]), np.ones((1, 1)))
    assert off_diagonal_absolute_mean(np.ones((1, 1))) == 0.0
    assert maximum_drawdown(np.asarray([0.1, -0.2, 0.05])) < 0
    assert hhi((0.0, 0.0)) == 0.0
    assert hhi((1.0, 1.0)) == pytest.approx(0.5)
