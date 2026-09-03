from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .numpy_preprocessing import apply_preprocessor, fit_preprocessor


@dataclass(frozen=True, slots=True)
class PointwiseRidgeRanker:
    alpha: float = 1.0
    implementation_id: str = "numpy_pointwise_ridge_v1"

    def fit(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        query_ids: list[str],
        candidate_ids: list[str],
    ) -> dict[str, object]:
        del query_ids, candidate_ids
        standardized, preprocessor = fit_preprocessor(features)
        intercept = float(np.mean(labels))
        centered = labels - intercept
        gram = standardized.T @ standardized + self.alpha * np.eye(standardized.shape[1])
        target = standardized.T @ centered
        try:
            coefficients = np.linalg.solve(gram, target)
        except np.linalg.LinAlgError:
            coefficients = np.linalg.lstsq(gram, target, rcond=None)[0]
        return {
            "implementation_id": self.implementation_id,
            **preprocessor,
            "coefficients": coefficients.astype(float).tolist(),
            "intercept": intercept,
            "pair_count": 0,
            "iterations": 1,
            "converged": True,
            "hyperparameters": {"alpha": self.alpha},
        }

    def predict(self, features: np.ndarray, state: dict[str, object]) -> np.ndarray:
        standardized = apply_preprocessor(features, state)
        coefficients = np.asarray(state["coefficients"], dtype=float)
        return standardized @ coefficients + float(state["intercept"])
