"""P9.S4.M04 — drawdown state machine and path-risk engine."""

from __future__ import annotations

import math

from .common import GrossNet, MetricRecord, MetricStatus, Unit, content_sha256, safe_mean
from .drawdown_models import (
    DrawdownEpisode,
    DrawdownEpisodePanel,
    DrawdownMetricPanel,
    DrawdownRequest,
    DrawdownResult,
    UnderwaterPoint,
    UnderwaterSeries,
)
from .reason_codes import ReasonCode


def compute_drawdowns(request: DrawdownRequest) -> DrawdownResult:
    """Detect non-overlapping drawdown episodes from the canonical net wealth path."""

    points = request.wealth_path.points
    identity = request.wealth_path.identity
    high_water = float(points[0].net_wealth)
    peak_time = points[0].timestamp
    current_peak_time = peak_time
    trough_time = peak_time
    current_min = 0.0
    episode_open = False
    underwater: list[UnderwaterPoint] = []
    episodes: list[DrawdownEpisode] = []
    episode_number = 0

    for point in points:
        wealth = float(point.net_wealth)
        if wealth >= high_water:
            drawdown = 0.0
            if episode_open:
                episode_number += 1
                episodes.append(
                    DrawdownEpisode(
                        episode_id=f"dd-{episode_number:04d}",
                        peak_time=current_peak_time,
                        trough_time=trough_time,
                        recovery_time=point.timestamp,
                        maximum_drawdown_fraction=current_min,
                        duration_seconds=int((point.timestamp - current_peak_time).total_seconds()),
                        recovery_seconds=int((point.timestamp - trough_time).total_seconds()),
                        censored=False,
                    )
                )
                episode_open = False
            high_water = wealth
            peak_time = point.timestamp
            current_peak_time = peak_time
            trough_time = peak_time
            current_min = 0.0
        else:
            drawdown = wealth / high_water - 1.0 if high_water != 0 else 0.0
            if not episode_open:
                episode_open = True
                current_peak_time = peak_time
                current_min = drawdown
                trough_time = point.timestamp
            elif drawdown < current_min:
                current_min = drawdown
                trough_time = point.timestamp
        underwater.append(
            UnderwaterPoint(
                timestamp=point.timestamp,
                high_water_mark=high_water,
                wealth=wealth,
                drawdown_fraction=drawdown,
            )
        )

    limitations: list[str] = []
    if episode_open:
        episode_number += 1
        limitations.append(ReasonCode.OPEN_EPISODE_CENSORED.value)
        episodes.append(
            DrawdownEpisode(
                episode_id=f"dd-{episode_number:04d}",
                peak_time=current_peak_time,
                trough_time=trough_time,
                recovery_time=None,
                maximum_drawdown_fraction=current_min,
                duration_seconds=int((points[-1].timestamp - current_peak_time).total_seconds()),
                recovery_seconds=None,
                censored=True,
            )
        )

    depths = [abs(episode.maximum_drawdown_fraction) for episode in episodes]
    max_drawdown = max(depths, default=0.0)
    average_drawdown = safe_mean(depths) if depths else 0.0
    if depths:
        count = max(1, math.ceil(len(depths) * request.policy.conditional_tail_fraction))
        conditional = safe_mean(sorted(depths, reverse=True)[:count])
    else:
        conditional = 0.0
    total_span = max(1.0, (points[-1].timestamp - points[0].timestamp).total_seconds())
    underwater_seconds = 0.0
    for left, right in zip(underwater, underwater[1:]):
        if left.drawdown_fraction < 0:
            underwater_seconds += (right.timestamp - left.timestamp).total_seconds()
    time_underwater = underwater_seconds / total_span
    max_duration = max((episode.duration_seconds for episode in episodes), default=0)
    recovered = [episode.recovery_seconds for episode in episodes if episode.recovery_seconds is not None]
    max_recovery = max(recovered, default=0)

    metrics = (
        MetricRecord(metric_id="drawdown.maximum", metric_version="1.0.0", producer_module_id="P9.S4.M04", value=max_drawdown, unit=Unit.FRACTION, status=MetricStatus.QUALIFIED, gross_net=GrossNet.NET, sample_count=len(points), method="high_water_mark_state_machine"),
        MetricRecord(metric_id="drawdown.average", metric_version="1.0.0", producer_module_id="P9.S4.M04", value=average_drawdown, unit=Unit.FRACTION, status=MetricStatus.QUALIFIED, gross_net=GrossNet.NET, sample_count=len(episodes), method="episode_mean"),
        MetricRecord(metric_id="drawdown.conditional_expected", metric_version="1.0.0", producer_module_id="P9.S4.M04", value=conditional, unit=Unit.FRACTION, status=MetricStatus.QUALIFIED, gross_net=GrossNet.NET, sample_count=len(episodes), method="worst_episode_tail_mean"),
        MetricRecord(metric_id="drawdown.maximum_duration", metric_version="1.0.0", producer_module_id="P9.S4.M04", value=float(max_duration), unit=Unit.SECONDS, status=MetricStatus.QUALIFIED, gross_net=GrossNet.NET, sample_count=len(episodes), method="episode_duration"),
        MetricRecord(metric_id="drawdown.maximum_recovery", metric_version="1.0.0", producer_module_id="P9.S4.M04", value=float(max_recovery), unit=Unit.SECONDS, status=MetricStatus.LIMITED if limitations else MetricStatus.QUALIFIED, gross_net=GrossNet.NET, sample_count=len(recovered), method="closed_episode_recovery", limitations=tuple(limitations)),
        MetricRecord(metric_id="drawdown.time_underwater", metric_version="1.0.0", producer_module_id="P9.S4.M04", value=time_underwater, unit=Unit.FRACTION, status=MetricStatus.QUALIFIED, gross_net=GrossNet.NET, sample_count=len(points), method="time_weighted_underwater"),
    )

    episode_body = {
        "panel_id": f"drawdown-episodes-{identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": (),
        "diagnostics": (),
        "limitations": tuple(limitations),
        "episodes": tuple(episodes),
    }
    episode_panel = DrawdownEpisodePanel(**episode_body, content_sha256=content_sha256(episode_body))
    metric_body = {
        "panel_id": f"drawdown-metrics-{identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": metrics,
        "diagnostics": (),
        "limitations": tuple(limitations),
        "open_episode_count": sum(episode.censored for episode in episodes),
    }
    metric_panel = DrawdownMetricPanel(**metric_body, content_sha256=content_sha256(metric_body))
    underwater_body = {
        "panel_id": f"underwater-{identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": (),
        "diagnostics": (),
        "limitations": tuple(limitations),
        "points": tuple(underwater),
    }
    underwater_panel = UnderwaterSeries(**underwater_body, content_sha256=content_sha256(underwater_body))
    return DrawdownResult(episodes=episode_panel, metrics=metric_panel, underwater=underwater_panel)
