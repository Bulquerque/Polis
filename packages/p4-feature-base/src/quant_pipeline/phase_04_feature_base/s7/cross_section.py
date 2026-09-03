from __future__ import annotations

import numpy as np
import pandas as pd


def normalize_values(
    values: dict[str, float], mode: str, epsilon: float
) -> tuple[dict[str, float], float | None, float | None, str]:
    if not values:
        return {}, None, None, "NO_OBSERVATIONS"
    ordered = sorted(values)
    array = np.asarray([values[key] for key in ordered], dtype=float)
    if mode == "none":
        return dict(values), None, None, "VALIDATED"
    if mode == "rank_percentile":
        ranks = pd.Series(array, index=ordered).rank(method="average", pct=True)
        return {key: float(ranks.loc[key]) for key in ordered}, None, None, "VALIDATED"
    if mode == "zscore":
        center, scale = float(np.mean(array)), float(np.std(array, ddof=0))
    else:
        center = float(np.median(array))
        q1, q3 = np.quantile(array, [0.25, 0.75])
        scale = float(q3 - q1)
    quality = "VALIDATED" if scale > epsilon else "DEGENERATE_SCALE"
    safe_scale = scale if scale > epsilon else 1.0
    normalized = {key: (values[key] - center) / safe_scale for key in ordered}
    return normalized, center, safe_scale, quality


def neutralize_values(
    values: dict[str, float],
    exposures: dict[str, dict[str, float | None]],
    names: tuple[str, ...],
    ridge_alpha: float,
    min_entities: int,
) -> tuple[dict[str, float], dict[str, float], int, int | None, str]:
    entities = [
        entity
        for entity in sorted(values)
        if entity in exposures
        and all(exposures[entity].get(name) is not None for name in names)
    ]
    minimum = max(min_entities, len(names) + 2)
    if len(entities) < minimum:
        return {}, {}, len(entities), None, "INSUFFICIENT_ENTITIES"
    x_raw = np.asarray([[float(exposures[e][name]) for name in names] for e in entities])
    x = np.column_stack([np.ones(len(entities)), x_raw])
    y = np.asarray([values[e] for e in entities], dtype=float)
    x_fit, y_fit = _ridge_augmented_system(x, y, len(names), ridge_alpha)
    beta, _, rank, _ = np.linalg.lstsq(x_fit, y_fit, rcond=None)
    residuals = y - x @ beta
    coefficients = {"intercept": float(beta[0])}
    coefficients.update({name: float(beta[index + 1]) for index, name in enumerate(names)})
    return dict(zip(entities, residuals, strict=True)), coefficients, len(entities), int(rank), "VALIDATED"


def _ridge_augmented_system(
    x: np.ndarray, y: np.ndarray, exposure_count: int, ridge_alpha: float
) -> tuple[np.ndarray, np.ndarray]:
    if ridge_alpha <= 0:
        return x, y
    penalty = np.diag([0.0] + [ridge_alpha**0.5] * exposure_count)
    return np.vstack([x, penalty]), np.concatenate([y, np.zeros(exposure_count + 1)])
