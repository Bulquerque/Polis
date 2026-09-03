"""Drawdown path and episode diagnostics from a positive price series."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from .ports import QuantDataError
from .series import MarketBar


def drawdown_diagnostics(
    bars: Sequence[MarketBar],
    *,
    wealth_start: float,
) -> tuple[dict[str, float | int | str | None], tuple[dict[str, float | str], ...]]:
    if not bars:
        raise QuantDataError("drawdown requires at least one bar")
    initial_close = bars[0].close
    peak_wealth = wealth_start
    peak_time = bars[0].observation_time
    max_drawdown = 0.0
    max_peak_time = peak_time
    trough_time = peak_time
    trough_index = 0
    path: list[dict[str, float | str]] = []
    for index, bar in enumerate(bars):
        wealth = wealth_start * bar.close / initial_close
        if wealth > peak_wealth:
            peak_wealth = wealth
            peak_time = bar.observation_time
        drawdown = wealth / peak_wealth - 1.0
        if drawdown < max_drawdown:
            max_drawdown = drawdown
            max_peak_time = peak_time
            trough_time = bar.observation_time
            trough_index = index
        path.append(
            {
                "observation_time": bar.observation_time.isoformat(),
                "wealth": wealth,
                "drawdown": drawdown,
            }
        )
    recovery_time: datetime | None = None
    peak_wealth_at_episode = wealth_start * next(
        bar.close for bar in bars if bar.observation_time == max_peak_time
    ) / initial_close
    for bar in bars[trough_index + 1 :]:
        wealth = wealth_start * bar.close / initial_close
        if wealth >= peak_wealth_at_episode:
            recovery_time = bar.observation_time
            break
    metrics: dict[str, float | int | str | None] = {
        "maximum_drawdown": max_drawdown,
        "current_drawdown": float(path[-1]["drawdown"]),
        "peak_time": max_peak_time.isoformat(),
        "trough_time": trough_time.isoformat(),
        "recovery_time": None if recovery_time is None else recovery_time.isoformat(),
        "episode_observations_to_trough": trough_index + 1,
        "observation_count": len(bars),
    }
    return metrics, tuple(path)
