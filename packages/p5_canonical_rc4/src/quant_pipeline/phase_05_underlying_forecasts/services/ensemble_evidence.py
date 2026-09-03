"""Out-of-sample residual evidence for pruning and non-negative stacking."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
from scipy.optimize import minimize

from ..domain.forecast import OOFValidationObservationPanel
from ..errors import DataQualityError

_EPS = 1e-12


def validation_profiles(
    observations: OOFValidationObservationPanel | None,
) -> dict[tuple[str, str, str, str, str], dict[Any, tuple[float, float]]]:
    profiles: dict[tuple[str, str, str, str, str], dict[Any, tuple[float, float]]] = defaultdict(dict)
    if observations is None:
        return profiles
    for row in observations.records:
        if row.partition_id != "VALIDATION":
            continue
        key = (row.resolver_id, row.underlying, row.target_id, row.horizon, row.unit)
        profiles[key][row.prediction_timestamp] = (float(row.prediction), float(row.realized))
    return profiles


def aligned_matrix(
    profiles: dict[tuple[str, str, str, str, str], dict[Any, tuple[float, float]]],
    resolver_ids: list[str],
    *,
    underlying: str,
    target_id: str,
    horizon: str,
    unit: str,
) -> tuple[np.ndarray, np.ndarray, list[Any]] | None:
    keys = [(resolver, underlying, target_id, horizon, unit) for resolver in resolver_ids]
    if any(key not in profiles for key in keys):
        return None
    common = set.intersection(*(set(profiles[key]) for key in keys))
    if len(common) < 12:
        return None
    ordered = sorted(common)
    predictions = np.column_stack([
        [profiles[key][timestamp][0] for timestamp in ordered] for key in keys
    ])
    realized_columns = np.column_stack([
        [profiles[key][timestamp][1] for timestamp in ordered] for key in keys
    ])
    realized = np.mean(realized_columns, axis=1)
    if np.max(np.ptp(realized_columns, axis=1)) > 1e-10:
        raise DataQualityError("aligned OOF resolvers disagree on realized outcomes")
    return predictions, realized, ordered


def pairwise_evidence(
    predictions: np.ndarray,
    realized: np.ndarray,
    resolver_ids: list[str],
) -> list[dict[str, Any]]:
    errors = realized[:, None] - predictions
    scale = np.maximum(np.std(errors, axis=0, ddof=0), 1e-8)
    failures = np.abs(errors) > 1.5 * scale
    output = []
    for left in range(len(resolver_ids)):
        for right in range(left + 1, len(resolver_ids)):
            correlation = float(np.corrcoef(errors[:, left], errors[:, right])[0, 1])
            cofailure = float(np.mean(failures[:, left] & failures[:, right]))
            output.append({
                "left_resolver_id": resolver_ids[left],
                "right_resolver_id": resolver_ids[right],
                "residual_correlation": correlation,
                "absolute_residual_correlation": abs(correlation),
                "cofailure_rate": cofailure,
            })
    return output


def model_confidence_set(
    predictions: np.ndarray,
    realized: np.ndarray,
    resolver_ids: list[str],
) -> dict[str, Any]:
    losses = (realized[:, None] - predictions) ** 2
    means = np.mean(losses, axis=0)
    best = float(np.min(means))
    standard_errors = np.std(losses, axis=0, ddof=1) / np.sqrt(len(losses))
    threshold = best + 1.96 * float(np.max(standard_errors))
    included = [resolver_ids[index] for index, value in enumerate(means) if float(value) <= threshold]
    return {
        "resolver_ids": included,
        "best_mse": best,
        "inclusion_threshold": threshold,
        "procedure": "LOSS_CONFIDENCE_SET_NORMAL_APPROXIMATION",
        "sample_size": len(losses),
    }


def marginal_contributions(
    predictions: np.ndarray,
    realized: np.ndarray,
    resolver_ids: list[str],
) -> list[dict[str, Any]]:
    full = np.mean(predictions, axis=1)
    full_mse = float(np.mean((realized - full) ** 2))
    output = []
    for index, resolver in enumerate(resolver_ids):
        if len(resolver_ids) == 1:
            without_mse = full_mse
        else:
            without = np.mean(np.delete(predictions, index, axis=1), axis=1)
            without_mse = float(np.mean((realized - without) ** 2))
        output.append({
            "resolver_id": resolver,
            "marginal_contribution": without_mse - full_mse,
            "replaceability": float(max(0.0, 1.0 - (without_mse - full_mse) / max(without_mse, _EPS))),
        })
    return output


def stacking_weights(predictions: np.ndarray, realized: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    if predictions.ndim != 2 or len(predictions) < 12 or predictions.shape[1] < 1:
        raise DataQualityError("stacking requires an aligned OOF prediction matrix")
    members = predictions.shape[1]
    initial = np.full(members, 1.0 / members, dtype=float)

    def objective(weights: np.ndarray) -> float:
        residuals = realized - predictions @ weights
        return float(np.mean(residuals**2) + 1e-8 * np.sum(weights**2))

    result = minimize(
        objective,
        initial,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * members,
        constraints={"type": "eq", "fun": lambda value: float(np.sum(value) - 1.0)},
        options={"maxiter": 200, "ftol": 1e-12, "disp": False},
    )
    if not result.success or not np.all(np.isfinite(result.x)):
        return initial, {"status": "FALLBACK_EQUAL", "message": str(result.message)}
    weights = np.maximum(np.asarray(result.x, dtype=float), 0.0)
    weights /= np.sum(weights)
    return weights, {
        "status": "OPTIMUM_FOUND",
        "objective": objective(weights),
        "iterations": int(result.nit),
        "solver": "SLSQP_NON_NEGATIVE_SIMPLEX",
    }


def compare_weighting_schemes(
    predictions: np.ndarray,
    realized: np.ndarray,
    inverse_weights: np.ndarray,
    stacking: np.ndarray,
) -> dict[str, float | str]:
    inverse_mse = float(np.mean((realized - predictions @ inverse_weights) ** 2))
    stacking_mse = float(np.mean((realized - predictions @ stacking) ** 2))
    selected = "NON_NEGATIVE_STACKING" if stacking_mse + 1e-12 < inverse_mse else "INVERSE_VALIDATION_LOSS"
    return {
        "selected": selected,
        "inverse_validation_mse": inverse_mse,
        "stacking_validation_mse": stacking_mse,
    }
