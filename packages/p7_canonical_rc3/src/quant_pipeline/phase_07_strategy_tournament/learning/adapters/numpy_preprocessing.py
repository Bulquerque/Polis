from __future__ import annotations

import numpy as np


def fit_preprocessor(features: np.ndarray) -> tuple[np.ndarray, dict[str, list[float]]]:
    medians = np.nanmedian(features, axis=0)
    medians = np.where(np.isfinite(medians), medians, 0.0)
    filled = np.where(np.isnan(features), medians, features)
    means = np.mean(filled, axis=0)
    scales = np.std(filled, axis=0)
    scales = np.where(scales > 1e-12, scales, 1.0)
    standardized = (filled - means) / scales
    state = {
        "imputation_medians": medians.astype(float).tolist(),
        "feature_means": means.astype(float).tolist(),
        "feature_scales": scales.astype(float).tolist(),
    }
    return standardized, state


def apply_preprocessor(features: np.ndarray, state: dict[str, object]) -> np.ndarray:
    medians = np.asarray(state["imputation_medians"], dtype=float)
    means = np.asarray(state["feature_means"], dtype=float)
    scales = np.asarray(state["feature_scales"], dtype=float)
    filled = np.where(np.isnan(features), medians, features)
    return (filled - means) / scales
