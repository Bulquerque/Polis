from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import numpy as np

from .contracts import EvidenceReference, SamplingUnit, S5State, content_sha256
from .models import (
    DependenceDiagnosticsRequest,
    DependenceDiagnosticsResult,
    LjungBoxDiagnostic,
    SeriesDependenceDiagnostic,
    TradeOverlapDiagnostic,
)
from .numerics import (
    autocorrelation,
    dependence_horizon,
    effective_sample_size,
    ljung_box,
    off_diagonal_absolute_mean,
    stable_correlation,
    to_float_matrix,
)

MODULE_ID = "P9.S5.M01"


def _regular_interval_seconds(timestamps: tuple[datetime, ...], tolerance: float) -> float | None:
    deltas = np.asarray(
        [(right - left).total_seconds() for left, right in zip(timestamps, timestamps[1:])],
        dtype=np.float64,
    )
    if deltas.size == 0 or np.any(deltas <= 0):
        return None
    median = float(np.median(deltas))
    if float(np.max(np.abs(deltas - median))) > tolerance:
        return None
    return median


def _cluster_overlapping_intervals(
    episodes: Iterable[tuple[str, datetime, datetime]],
) -> tuple[tuple[tuple[str, int], ...], int, int]:
    ordered = sorted(episodes, key=lambda item: (item[1], item[2], item[0]))
    if not ordered:
        return (), 0, 0
    assignments: list[tuple[str, int]] = []
    cluster_id = 0
    cluster_end: datetime | None = None
    events: list[tuple[datetime, int]] = []
    for trade_id, opened_at, closed_at in ordered:
        if cluster_end is None or opened_at > cluster_end:
            cluster_id += 1
            cluster_end = closed_at
        else:
            cluster_end = max(cluster_end, closed_at)
        assignments.append((trade_id, cluster_id))
        events.append((opened_at, 1))
        events.append((closed_at, -1))
    active = 0
    maximum_concurrency = 0
    for _, delta in sorted(events, key=lambda item: (item[0], -item[1])):
        active += delta
        maximum_concurrency = max(maximum_concurrency, active)
    return tuple(assignments), cluster_id, maximum_concurrency


def _diagnose_series(
    request: DependenceDiagnosticsRequest,
) -> tuple[SeriesDependenceDiagnostic, ...]:
    matrix = to_float_matrix(request.series.values)
    nobs = matrix.shape[0]
    diagnostics: list[SeriesDependenceDiagnostic] = []
    for column_index, series_id in enumerate(request.series.series_ids):
        values = matrix[:, column_index]
        selected_max_lag = min(request.policy.maximum_lag, nobs - 1)
        acf = autocorrelation(values, selected_max_lag)
        portmanteau = tuple(
            LjungBoxDiagnostic(lag=lag, statistic=statistic, pvalue=pvalue)
            for lag in request.policy.portmanteau_lags
            if lag < nobs
            for statistic, pvalue in (ljung_box(values, lag),)
        )
        diagnostics.append(
            SeriesDependenceDiagnostic(
                series_id=series_id,
                observation_count=nobs,
                effective_sample_size=effective_sample_size(values, selected_max_lag),
                dependence_horizon=dependence_horizon(values, selected_max_lag),
                autocorrelations=tuple(float(value) for value in acf),
                ljung_box=portmanteau,
                variance=float(np.var(values, ddof=1)),
            )
        )
    return tuple(diagnostics)


def _diagnose_trade_overlap(request: DependenceDiagnosticsRequest) -> TradeOverlapDiagnostic | None:
    if request.trades is None:
        return None
    assignments, cluster_count, maximum_concurrency = _cluster_overlapping_intervals(
        (episode.trade_id, episode.opened_at, episode.closed_at)
        for episode in request.trades.episodes
    )
    trade_count = len(request.trades.episodes)
    cluster_sizes = {
        cluster: sum(candidate == cluster for _, candidate in assignments)
        for _, cluster in assignments
    }
    overlapping = sum(cluster_sizes[cluster] > 1 for _, cluster in assignments)
    overlap_fraction = overlapping / trade_count if trade_count else 0.0
    return TradeOverlapDiagnostic(
        trade_count=trade_count,
        cluster_count=cluster_count,
        maximum_concurrency=maximum_concurrency,
        overlap_fraction=overlap_fraction,
        cluster_ids_by_trade=assignments,
    )


def _qualified_status(reason_codes: list[str]) -> S5State:
    if "P9_BOOTSTRAP_INSUFFICIENT_OBSERVATIONS" in reason_codes:
        return S5State.INSUFFICIENT_HISTORY
    if reason_codes:
        return S5State.QUALIFIED_WITH_LIMITATIONS
    return S5State.QUALIFIED


def diagnose_dependence(request: DependenceDiagnosticsRequest) -> DependenceDiagnosticsResult:
    """Diagnose temporal, cross-sectional and trade-overlap dependence."""

    matrix = to_float_matrix(request.series.values)
    nobs, nseries = matrix.shape
    interval_seconds = _regular_interval_seconds(
        request.series.timestamps,
        request.policy.irregularity_tolerance_seconds,
    )
    if interval_seconds is None:
        return DependenceDiagnosticsResult(
            status=S5State.IRREGULAR_TIME_UNSUPPORTED,
            series_diagnostics=(),
            cross_sectional_correlation=(),
            average_absolute_cross_correlation=0.0,
            trade_overlap=None,
            recommended_sampling_units=(),
            regular_interval_seconds=None,
            reason_codes=("P9_BOOTSTRAP_TIME_INDEX_INVALID",),
            limitations=("regular time spacing is required for the current block bootstrap",),
        )

    reason_codes: list[str] = []
    limitations: list[str] = []
    if nobs < request.policy.minimum_observations:
        reason_codes.append("P9_BOOTSTRAP_INSUFFICIENT_OBSERVATIONS")
    diagnostics = _diagnose_series(request)
    correlation = stable_correlation(matrix)
    average_correlation = off_diagonal_absolute_mean(correlation)
    recommended: list[SamplingUnit] = [SamplingUnit.TIME_BLOCK]
    if (
        nseries > 1
        and average_correlation >= request.policy.cross_sectional_high_correlation
    ):
        recommended.append(SamplingUnit.HIERARCHICAL_TIME_CROSS_SECTION)

    trade_overlap = _diagnose_trade_overlap(request)
    if trade_overlap is None:
        limitations.append("trade overlap diagnostics unavailable")
        reason_codes.append("P9_BOOTSTRAP_OVERLAP_METADATA_MISSING")
    elif trade_overlap.overlap_fraction > 0.0:
        recommended.append(SamplingUnit.TRADE_EPISODE_CLUSTER)

    evidence_hash = content_sha256(
        {
            "module_id": MODULE_ID,
            "series_panel_id": request.series.panel_id,
            "series_diagnostics": [item.model_dump(mode="json") for item in diagnostics],
            "correlation": correlation.tolist(),
            "trade_overlap": trade_overlap.model_dump(mode="json") if trade_overlap else None,
        }
    )
    return DependenceDiagnosticsResult(
        status=_qualified_status(reason_codes),
        series_diagnostics=diagnostics,
        cross_sectional_correlation=tuple(
            tuple(float(value) for value in row) for row in correlation
        ),
        average_absolute_cross_correlation=float(average_correlation),
        trade_overlap=trade_overlap,
        recommended_sampling_units=tuple(dict.fromkeys(recommended)),
        regular_interval_seconds=interval_seconds,
        reason_codes=tuple(reason_codes),
        limitations=tuple(limitations),
        evidence=(
            EvidenceReference(
                evidence_id=f"{MODULE_ID}:{request.series.panel_id}",
                evidence_type="DEPENDENCE_DIAGNOSTIC",
                content_sha256=evidence_hash,
            ),
        ),
    )
