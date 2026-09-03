from __future__ import annotations

import math

import numpy as np

from .contracts import S5State
from .models import (
    BlockLengthEstimate,
    BlockLengthSelectionRequest,
    BlockLengthSelectionResult,
)
from .numerics import to_float_matrix

MODULE_ID = "P9.S5.M02"


def _optimal_block_length(values: np.ndarray) -> tuple[float, float]:
    """Politis-White block length with the Patton-Politis-White correction."""

    nobs = values.shape[0]
    eps = values - values.mean()
    if float(eps @ eps) <= np.finfo(np.float64).eps:
        return 1.0, 1.0
    b_max = float(np.ceil(min(3.0 * np.sqrt(nobs), nobs / 3.0)))
    kn = max(5, int(np.log10(nobs)))
    m_max = min(int(np.ceil(np.sqrt(nobs))) + kn, nobs - 2)
    if m_max < 1:
        return 1.0, 1.0
    critical_value = 2.0 * np.sqrt(np.log10(nobs) / nobs)
    autocovariances = np.zeros(m_max + 1, dtype=np.float64)
    absolute_autocorrelations = np.zeros(m_max + 1, dtype=np.float64)
    optimal_m: int | None = None
    for lag in range(m_max + 1):
        cross_product = float(eps[lag:] @ eps[: nobs - lag])
        autocovariances[lag] = cross_product / nobs
        if lag == 0:
            absolute_autocorrelations[lag] = 1.0
        else:
            left = eps[lag:]
            right = eps[: nobs - lag]
            denominator = float(np.sqrt((left @ left) * (right @ right)))
            absolute_autocorrelations[lag] = (
                abs(cross_product) / denominator if denominator > np.finfo(np.float64).eps else 0.0
            )
        if lag >= kn and optimal_m is None:
            if np.all(absolute_autocorrelations[lag - kn : lag] < critical_value):
                optimal_m = lag - kn
    selected_m = 2 * max(optimal_m, 1) if optimal_m is not None else m_max
    selected_m = min(selected_m, m_max)
    g_value = 0.0
    long_run_autocovariance = autocovariances[0]
    for lag in range(1, selected_m + 1):
        ratio = lag / selected_m
        lambda_weight = 1.0 if ratio <= 0.5 else 2.0 * (1.0 - ratio)
        g_value += 2.0 * lambda_weight * lag * autocovariances[lag]
        long_run_autocovariance += 2.0 * lambda_weight * autocovariances[lag]
    if (
        abs(long_run_autocovariance) <= np.finfo(np.float64).eps
        or abs(g_value) <= np.finfo(np.float64).eps
    ):
        return 1.0, 1.0
    stationary_denominator = 2.0 * long_run_autocovariance**2
    circular_denominator = (4.0 / 3.0) * long_run_autocovariance**2
    stationary = ((2.0 * g_value**2) / stationary_denominator) ** (1.0 / 3.0) * nobs ** (1.0 / 3.0)
    circular = ((2.0 * g_value**2) / circular_denominator) ** (1.0 / 3.0) * nobs ** (1.0 / 3.0)
    return min(float(stationary), b_max), min(float(circular), b_max)


def _bounded_integer(value: float, *, lower: int, upper: int) -> int:
    return int(np.clip(math.ceil(value), lower, upper))


def select_block_length(request: BlockLengthSelectionRequest) -> BlockLengthSelectionResult:
    """Select per-series and joint block lengths."""

    matrix = to_float_matrix(request.series.values)
    nobs = matrix.shape[0]
    upper = max(
        request.policy.minimum_block_length,
        int(math.floor(nobs * request.policy.maximum_fraction)),
    )
    diagnostics = {item.series_id: item for item in request.diagnostics.series_diagnostics}
    estimates: list[BlockLengthEstimate] = []
    limitations: list[str] = []
    for column_index, series_id in enumerate(request.series.series_ids):
        stationary_raw, circular_raw = _optimal_block_length(matrix[:, column_index])
        diagnostic = diagnostics.get(series_id)
        horizon = diagnostic.dependence_horizon if diagnostic is not None else 1
        used_fallback = stationary_raw <= 1.0 and circular_raw <= 1.0 and horizon > 1
        if used_fallback:
            fallback = horizon * request.policy.fallback_dependence_multiplier
            stationary_raw = max(stationary_raw, fallback)
            circular_raw = max(circular_raw, fallback)
            limitations.append(f"fallback block length used for {series_id}")
        stationary_selected = _bounded_integer(
            stationary_raw,
            lower=request.policy.minimum_block_length,
            upper=upper,
        )
        circular_selected = _bounded_integer(
            circular_raw,
            lower=request.policy.minimum_block_length,
            upper=upper,
        )
        moving_selected = circular_selected
        estimates.append(
            BlockLengthEstimate(
                series_id=series_id,
                stationary_raw=float(stationary_raw),
                circular_raw=float(circular_raw),
                moving_selected=moving_selected,
                stationary_selected=stationary_selected,
                circular_selected=circular_selected,
                dependence_horizon=horizon,
                used_fallback=used_fallback,
            )
        )
    if request.policy.joint_aggregation == "MAX":
        aggregator = max
    else:
        aggregator = lambda values: int(math.ceil(float(np.median(tuple(values)))))
    moving_joint = int(aggregator(item.moving_selected for item in estimates))
    stationary_joint = int(aggregator(item.stationary_selected for item in estimates))
    circular_joint = int(aggregator(item.circular_selected for item in estimates))
    status = S5State.SUCCESS if not limitations else S5State.QUALIFIED_WITH_LIMITATIONS
    return BlockLengthSelectionResult(
        status=status,
        estimates=tuple(estimates),
        joint_moving_block_length=moving_joint,
        joint_stationary_block_length=stationary_joint,
        joint_circular_block_length=circular_joint,
        reason_codes=("P9_BOOTSTRAP_BLOCK_LENGTH_FALLBACK",) if limitations else (),
        limitations=tuple(limitations),
    )
