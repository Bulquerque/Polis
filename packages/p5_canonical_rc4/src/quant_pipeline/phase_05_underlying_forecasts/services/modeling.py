"""Portable JSON-serializable model training and prediction."""
from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from ..errors import TrainingError
from .sklearn_resolvers import ExtraTreesResolver, HistogramGradientBoostingResolver


class Resolver(Protocol):
    implementation_id: str

    def fit(self, x: np.ndarray, y: np.ndarray, parameters: dict[str, Any], seed: int) -> dict[str, Any]: ...

    def predict(self, model: dict[str, Any], x: np.ndarray) -> np.ndarray: ...


class MeanResolver:
    implementation_id = "builtin.mean"

    def fit(self, x: np.ndarray, y: np.ndarray, parameters: dict[str, Any], seed: int) -> dict[str, Any]:
        mean = float(np.mean(y))
        median = float(np.median(y))
        weight = len(y) / (len(y) + 20.0)
        estimate = weight * mean + (1.0 - weight) * median
        return {
            "kind": "shrinkage_location", "mean": mean, "median": median,
            "shrinkage_weight": weight, "estimate": estimate, "feature_count": int(x.shape[1]),
        }

    def predict(self, model: dict[str, Any], x: np.ndarray) -> np.ndarray:
        return np.full(x.shape[0], float(model.get("estimate", model["mean"])), dtype=float)


class RidgeResolver:
    implementation_id = "builtin.ridge"

    def fit(self, x: np.ndarray, y: np.ndarray, parameters: dict[str, Any], seed: int) -> dict[str, Any]:
        alpha = float(parameters.get("alpha", 1.0))
        if alpha < 0:
            raise TrainingError("ridge alpha must be nonnegative")
        mean = np.mean(x, axis=0)
        scale = np.std(x, axis=0)
        safe_scale = np.where(scale > 1e-12, scale, 1.0)
        design = np.column_stack([np.ones(x.shape[0]), (x - mean) / safe_scale])
        penalty = np.eye(design.shape[1]) * alpha
        penalty[0, 0] = 0.0
        coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ y)
        return {
            "kind": "ridge",
            "intercept": float(coefficients[0]),
            "weights": coefficients[1:].tolist(),
            "mean": mean.tolist(),
            "scale": safe_scale.tolist(),
            "alpha": alpha,
        }

    def predict(self, model: dict[str, Any], x: np.ndarray) -> np.ndarray:
        mean = np.asarray(model["mean"], dtype=float)
        scale = np.asarray(model["scale"], dtype=float)
        weights = np.asarray(model["weights"], dtype=float)
        return float(model["intercept"]) + ((x - mean) / scale) @ weights


class HuberIRLSResolver:
    """Robust linear resolver using bounded Huber iteratively reweighted least squares."""

    implementation_id = "builtin.huber_irls"

    def fit(self, x: np.ndarray, y: np.ndarray, parameters: dict[str, Any], seed: int) -> dict[str, Any]:
        delta = float(parameters.get("delta", 1.345))
        ridge = float(parameters.get("ridge", 1e-4))
        iterations = int(parameters.get("max_iter", 40))
        if delta <= 0 or ridge < 0 or not 5 <= iterations <= 100:
            raise TrainingError("invalid Huber IRLS parameters")
        mean = np.mean(x, axis=0)
        scale = np.where(np.std(x, axis=0) > 1e-12, np.std(x, axis=0), 1.0)
        design = np.column_stack([np.ones(x.shape[0]), (x - mean) / scale])
        penalty = np.eye(design.shape[1]) * ridge
        penalty[0, 0] = 0.0
        beta = np.linalg.solve(design.T @ design + penalty, design.T @ y)
        for _ in range(iterations):
            residual = y - design @ beta
            robust_scale = max(float(np.median(np.abs(residual))) / 0.6745, 1e-8)
            standardized = np.abs(residual) / robust_scale
            weights = np.where(standardized <= delta, 1.0, delta / np.maximum(standardized, 1e-12))
            weighted = design * np.sqrt(weights)[:, None]
            target = y * np.sqrt(weights)
            updated = np.linalg.solve(weighted.T @ weighted + penalty, weighted.T @ target)
            if np.max(np.abs(updated - beta)) < 1e-10:
                beta = updated
                break
            beta = updated
        return {
            "kind": "huber_irls", "intercept": float(beta[0]), "weights": beta[1:].tolist(),
            "mean": mean.tolist(), "scale": scale.tolist(), "delta": delta, "ridge": ridge,
        }

    def predict(self, model: dict[str, Any], x: np.ndarray) -> np.ndarray:
        mean = np.asarray(model["mean"], dtype=float)
        scale = np.asarray(model["scale"], dtype=float)
        weights = np.asarray(model["weights"], dtype=float)
        return float(model["intercept"]) + ((x - mean) / scale) @ weights


class KalmanDLMResolver:
    """CPU-first dynamic linear model with random-walk coefficients."""

    implementation_id = "builtin.kalman_dlm"

    def fit(self, x: np.ndarray, y: np.ndarray, parameters: dict[str, Any], seed: int) -> dict[str, Any]:
        process_scale = float(parameters.get("process_scale", 1e-4))
        observation_scale = float(parameters.get("observation_scale", 1e-3))
        ridge = float(parameters.get("ridge", 1.0))
        if process_scale <= 0 or observation_scale <= 0 or ridge <= 0:
            raise TrainingError("DLM scales and ridge must be positive")
        design = np.column_stack([np.ones(x.shape[0]), x])
        state = np.zeros(design.shape[1], dtype=float)
        covariance = np.eye(design.shape[1], dtype=float) / ridge
        process = np.eye(design.shape[1], dtype=float) * process_scale
        innovations: list[float] = []
        for row, target in zip(design, y, strict=True):
            prior_covariance = covariance + process
            innovation_variance = float(row @ prior_covariance @ row + observation_scale)
            gain = prior_covariance @ row / max(innovation_variance, 1e-12)
            innovation = float(target - row @ state)
            state = state + gain * innovation
            covariance = prior_covariance - np.outer(gain, row) @ prior_covariance
            covariance = (covariance + covariance.T) / 2.0
            innovations.append(innovation)
        return {
            "kind": "kalman_dlm", "state": state.tolist(),
            "state_covariance": covariance.tolist(), "process_scale": process_scale,
            "observation_scale": observation_scale,
            "innovation_std": float(np.std(innovations, ddof=0)),
        }

    def predict(self, model: dict[str, Any], x: np.ndarray) -> np.ndarray:
        state = np.asarray(model["state"], dtype=float)
        return np.column_stack([np.ones(x.shape[0]), x]) @ state


class KernelRidgeResolver:
    """Portable RBF kernel ridge challenger with bounded training dictionary."""

    implementation_id = "builtin.kernel_ridge_rbf"

    def fit(self, x: np.ndarray, y: np.ndarray, parameters: dict[str, Any], seed: int) -> dict[str, Any]:
        alpha = float(parameters.get("alpha", 1.0))
        gamma = float(parameters.get("gamma", 0.25))
        max_dictionary = int(parameters.get("max_dictionary", 256))
        if alpha <= 0 or gamma <= 0 or max_dictionary < 8:
            raise TrainingError("invalid kernel ridge parameters")
        if len(x) > max_dictionary:
            indices = np.linspace(0, len(x) - 1, max_dictionary, dtype=int)
            dictionary, targets = x[indices], y[indices]
        else:
            dictionary, targets = x, y
        mean = np.mean(dictionary, axis=0)
        scale = np.where(np.std(dictionary, axis=0) > 1e-12, np.std(dictionary, axis=0), 1.0)
        standardized = (dictionary - mean) / scale
        kernel = _rbf_kernel(standardized, standardized, gamma)
        dual = np.linalg.solve(kernel + np.eye(len(kernel)) * alpha, targets)
        return {
            "kind": "kernel_ridge_rbf", "dictionary": dictionary.tolist(),
            "dual": dual.tolist(), "mean": mean.tolist(), "scale": scale.tolist(),
            "alpha": alpha, "gamma": gamma,
        }

    def predict(self, model: dict[str, Any], x: np.ndarray) -> np.ndarray:
        dictionary = np.asarray(model["dictionary"], dtype=float)
        mean = np.asarray(model["mean"], dtype=float)
        scale = np.asarray(model["scale"], dtype=float)
        left = (x - mean) / scale
        right = (dictionary - mean) / scale
        kernel = _rbf_kernel(left, right, float(model["gamma"]))
        return kernel @ np.asarray(model["dual"], dtype=float)


def _rbf_kernel(left: np.ndarray, right: np.ndarray, gamma: float) -> np.ndarray:
    distances = np.sum((left[:, None, :] - right[None, :, :]) ** 2, axis=2)
    return np.exp(-gamma * distances)


_RESOLVERS: dict[str, Resolver] = {
    MeanResolver.implementation_id: MeanResolver(),
    RidgeResolver.implementation_id: RidgeResolver(),
    HuberIRLSResolver.implementation_id: HuberIRLSResolver(),
    KalmanDLMResolver.implementation_id: KalmanDLMResolver(),
    KernelRidgeResolver.implementation_id: KernelRidgeResolver(),
    HistogramGradientBoostingResolver.implementation_id: HistogramGradientBoostingResolver(),
    ExtraTreesResolver.implementation_id: ExtraTreesResolver(),
}


def get_resolver(implementation_id: str) -> Resolver:
    try:
        return _RESOLVERS[implementation_id]
    except KeyError as exc:
        raise TrainingError(f"unknown resolver implementation: {implementation_id}") from exc
