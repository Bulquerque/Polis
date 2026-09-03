from __future__ import annotations

from datetime import timedelta

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.contracts import S5State, TimeSeriesPanel
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m01_dependence_and_sampling_diagnostics import diagnose_dependence
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import DependenceDiagnosticsRequest


def test_dependence_diagnostics_detects_autocorrelation(context, series_panel, trade_panel) -> None:
    result = diagnose_dependence(
        DependenceDiagnosticsRequest(context=context, series=series_panel, trades=trade_panel)
    )
    assert result.status in {S5State.QUALIFIED, S5State.QUALIFIED_WITH_LIMITATIONS}
    strategy = next(item for item in result.series_diagnostics if item.series_id == "strategy")
    assert strategy.effective_sample_size < strategy.observation_count
    assert strategy.dependence_horizon >= 1
    assert result.trade_overlap is not None
    assert result.trade_overlap.maximum_concurrency >= 2
    assert result.evidence


def test_irregular_time_is_fail_closed(context, series_panel) -> None:
    timestamps = list(series_panel.timestamps)
    timestamps[20] = timestamps[19] + timedelta(hours=12)
    timestamps[21:] = [timestamp - timedelta(hours=12) for timestamp in timestamps[21:]]
    irregular = TimeSeriesPanel(
        **{
            **series_panel.model_dump(mode="python"),
            "timestamps": tuple(timestamps),
        }
    )
    result = diagnose_dependence(DependenceDiagnosticsRequest(context=context, series=irregular))
    assert result.status is S5State.IRREGULAR_TIME_UNSUPPORTED
    assert "P9_BOOTSTRAP_TIME_INDEX_INVALID" in result.reason_codes
