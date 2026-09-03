"""P8.S4.M02 dependence and tail-comovement engine."""
from __future__ import annotations

import numpy as np
from scipy.linalg import eigh

from ..arrays import DependenceArrays, ScenarioPnLCube
from ..contracts import ComponentQuality, DependencePolicy, DependenceSummary
from ..errors import NumericalIntegrityError

MODULE_ID = "P8.S4.M02"


def _weighted_covariance(values: np.ndarray, probabilities: np.ndarray) -> np.ndarray:
    mean = np.sum(values * probabilities[:, None], axis=0)
    centered = values - mean
    return (centered * probabilities[:, None]).T @ centered


def _weighted_quantile(values: np.ndarray, probabilities: np.ndarray, level: float) -> float:
    order = np.argsort(values, kind="stable")
    ordered_values = values[order]
    cumulative = np.cumsum(probabilities[order])
    index = int(np.searchsorted(cumulative, level, side="left"))
    return float(ordered_values[min(index, len(ordered_values) - 1)])


def _auto_shrinkage_alpha(effective_samples: float, dimension: int) -> float:
    if dimension <= 1:
        return 0.0
    return float(np.clip(dimension / (effective_samples + dimension), 0.0, 1.0))


def _shrink(covariance: np.ndarray, alpha: float) -> np.ndarray:
    target_level = float(np.trace(covariance) / max(len(covariance), 1))
    target = np.eye(len(covariance), dtype=np.float64) * target_level
    return (1.0 - alpha) * covariance + alpha * target


def _repair_psd(matrix: np.ndarray, floor: float) -> tuple[np.ndarray, float, float, float]:
    symmetric = 0.5 * (matrix + matrix.T)
    eigenvalues, eigenvectors = eigh(symmetric, check_finite=True)
    minimum_before = float(eigenvalues.min(initial=0.0))
    clipped = np.maximum(eigenvalues, floor)
    repaired = (eigenvectors * clipped) @ eigenvectors.T
    repaired = 0.5 * (repaired + repaired.T)
    denominator = max(float(np.linalg.norm(symmetric, ord="fro")), 1e-16)
    relative = float(np.linalg.norm(repaired - symmetric, ord="fro") / denominator)
    return repaired, minimum_before, float(clipped.min(initial=0.0)), relative


def _correlation(covariance: np.ndarray) -> np.ndarray:
    scale = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    denominator = np.outer(scale, scale)
    result = np.divide(covariance, denominator, out=np.zeros_like(covariance), where=denominator > 0.0)
    np.fill_diagonal(result, np.where(scale > 0.0, 1.0, 0.0))
    return np.clip(result, -1.0, 1.0)


def _tail_dependence(
    values: np.ndarray,
    probabilities: np.ndarray,
    probability: float,
) -> tuple[np.ndarray, np.ndarray]:
    candidate_count = values.shape[1]
    lower_thresholds = np.asarray([
        _weighted_quantile(values[:, index], probabilities, probability)
        for index in range(candidate_count)
    ])
    upper_thresholds = np.asarray([
        _weighted_quantile(values[:, index], probabilities, 1.0 - probability)
        for index in range(candidate_count)
    ])
    lower_events = values <= lower_thresholds[None, :]
    upper_events = values >= upper_thresholds[None, :]
    lower = np.empty((candidate_count, candidate_count), dtype=np.float64)
    upper = np.empty_like(lower)
    for left in range(candidate_count):
        for right in range(candidate_count):
            lower_joint = float(np.sum(probabilities * (lower_events[:, left] & lower_events[:, right])))
            upper_joint = float(np.sum(probabilities * (upper_events[:, left] & upper_events[:, right])))
            lower[left, right] = np.clip(lower_joint / probability, 0.0, 1.0)
            upper[left, right] = np.clip(upper_joint / probability, 0.0, 1.0)
    return lower, upper


def build_dependence(
    cube: ScenarioPnLCube,
    policy: DependencePolicy,
) -> tuple[DependenceArrays, DependenceSummary]:
    terminal = cube.candidate_pnl[:, -1, :]
    probabilities = cube.probabilities
    effective_samples = float(1.0 / np.sum(probabilities**2))
    covariance = _weighted_covariance(terminal, probabilities)
    alpha = policy.shrinkage_alpha
    if alpha is None:
        alpha = _auto_shrinkage_alpha(effective_samples, terminal.shape[1])
    shrunk = _shrink(covariance, alpha)
    repaired, minimum_before, minimum_after, relative_repair = _repair_psd(shrunk, policy.psd_floor)
    if not np.all(np.isfinite(repaired)):
        raise NumericalIntegrityError("dependence covariance is non-finite")
    lower, upper = _tail_dependence(terminal, probabilities, policy.tail_probability)
    reasons: list[str] = []
    quality = ComponentQuality.FULLY_QUALIFIED
    if effective_samples < policy.minimum_effective_samples:
        quality = ComponentQuality.DEGRADED
        reasons.append("TAIL_SAMPLE_INSUFFICIENT")
    if relative_repair > policy.max_psd_repair_relative:
        quality = ComponentQuality.DEGRADED
        reasons.append("PSD_REPAIR_EXCESSIVE")
    arrays = DependenceArrays(
        covariance=repaired,
        correlation=_correlation(repaired),
        lower_tail_dependence=lower,
        upper_tail_dependence=upper,
        tail_asymmetry=lower - upper,
        candidate_ids=cube.candidate_ids,
    )
    summary = DependenceSummary(
        covariance_method="WEIGHTED_DIAGONAL_SHRINKAGE",
        shrinkage_alpha=alpha,
        effective_sample_size=effective_samples,
        minimum_eigenvalue_before=minimum_before,
        minimum_eigenvalue_after=minimum_after,
        psd_repair_relative=relative_repair,
        quality=quality,
        reason_codes=tuple(reasons),
        content_sha256=arrays.content_sha256(),
    )
    return arrays, summary
