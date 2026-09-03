from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from .numpy_preprocessing import apply_preprocessor, fit_preprocessor


@dataclass(frozen=True, slots=True)
class PairwiseLinearRanker:
    alpha: float = 1.0
    max_iterations: int = 100
    tolerance: float = 1e-8
    label_tolerance: float = 1e-12
    max_pairs_per_query: int = 128
    max_pairs_total: int = 100_000

    implementation_id: str = "numpy_pairwise_linear_ranknet_v1"

    def _pairs(
        self,
        labels: np.ndarray,
        query_ids: list[str],
        candidate_ids: list[str],
    ) -> list[tuple[int, int, float]]:
        groups: dict[str, list[int]] = defaultdict(list)
        for index, query_id in enumerate(query_ids):
            groups[query_id].append(index)
        pairs: list[tuple[int, int, float]] = []
        for query_id in sorted(groups):
            indices = groups[query_id]
            local: list[tuple[int, int, float]] = []
            for left_pos, left in enumerate(indices):
                for right in indices[left_pos + 1 :]:
                    difference = float(labels[left] - labels[right])
                    if abs(difference) <= self.label_tolerance:
                        continue
                    better, worse = (left, right) if difference > 0 else (right, left)
                    local.append((better, worse, abs(difference)))
            local.sort(key=lambda pair: (-pair[2], candidate_ids[pair[0]], candidate_ids[pair[1]]))
            pairs.extend(local[: self.max_pairs_per_query])
        pairs.sort(key=lambda pair: (query_ids[pair[0]], -pair[2], candidate_ids[pair[0]], candidate_ids[pair[1]]))
        return pairs[: self.max_pairs_total]

    def fit(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        query_ids: list[str],
        candidate_ids: list[str],
    ) -> dict[str, object]:
        standardized, preprocessor = fit_preprocessor(features)
        pairs = self._pairs(labels, query_ids, candidate_ids)
        if not pairs:
            raise ValueError("pairwise ranker requires at least one non-tied pair")
        differences = np.vstack([standardized[better] - standardized[worse] for better, worse, _ in pairs])
        weights = np.asarray([weight for _, _, weight in pairs], dtype=float)
        weights /= max(float(np.mean(weights)), 1e-12)
        coefficients = np.zeros(standardized.shape[1], dtype=float)
        identity = np.eye(standardized.shape[1], dtype=float)
        converged = False
        iterations = 0
        for iterations in range(1, self.max_iterations + 1):
            margins = differences @ coefficients
            negative_probability = 1.0 / (1.0 + np.exp(np.clip(margins, -50.0, 50.0)))
            gradient = -(differences.T @ (weights * negative_probability)) / weights.sum()
            gradient += self.alpha * coefficients
            curvature = weights * negative_probability * (1.0 - negative_probability)
            hessian = (differences.T * curvature) @ differences / weights.sum() + self.alpha * identity
            try:
                step = np.linalg.solve(hessian, gradient)
            except np.linalg.LinAlgError:
                step = np.linalg.lstsq(hessian, gradient, rcond=None)[0]
            coefficients -= step
            if float(np.linalg.norm(step)) <= self.tolerance:
                converged = True
                break
        return {
            "implementation_id": self.implementation_id,
            **preprocessor,
            "coefficients": coefficients.astype(float).tolist(),
            "intercept": 0.0,
            "pair_count": len(pairs),
            "iterations": iterations,
            "converged": converged,
            "hyperparameters": {
                "alpha": self.alpha,
                "max_iterations": self.max_iterations,
                "tolerance": self.tolerance,
                "label_tolerance": self.label_tolerance,
                "max_pairs_per_query": self.max_pairs_per_query,
                "max_pairs_total": self.max_pairs_total,
            },
        }

    def predict(self, features: np.ndarray, state: dict[str, object]) -> np.ndarray:
        standardized = apply_preprocessor(features, state)
        coefficients = np.asarray(state["coefficients"], dtype=float)
        return standardized @ coefficients + float(state.get("intercept", 0.0))
