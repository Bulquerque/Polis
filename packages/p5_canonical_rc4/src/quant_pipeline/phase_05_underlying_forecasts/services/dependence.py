"""Covariance, dynamic dependence and network diagnostics."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

import numpy as np
from sklearn.covariance import LedoitWolf, OAS

from ..errors import DataQualityError, NumericalError


def sample_covariance(values: np.ndarray) -> np.ndarray:
    _validate_matrix(values)
    return _symmetric(np.cov(values, rowvar=False, ddof=1))


def ewma_covariance(values: np.ndarray, decay: float = 0.94) -> np.ndarray:
    _validate_matrix(values)
    if not 0.0 < decay < 1.0:
        raise ValueError("EWMA decay must be between zero and one")
    count = values.shape[0]
    weights = (1.0 - decay) * decay ** np.arange(count - 1, -1, -1, dtype=float)
    weights /= weights.sum()
    centered = values - np.sum(values * weights[:, None], axis=0)
    covariance = (centered * weights[:, None]).T @ centered
    correction = 1.0 - float(np.sum(weights**2))
    return _symmetric(covariance / max(correction, 1e-12))


def shrinkage_covariances(values: np.ndarray) -> dict[str, np.ndarray]:
    _validate_matrix(values)
    return {
        "SAMPLE": sample_covariance(values),
        "EWMA": ewma_covariance(values),
        "LEDOIT_WOLF": _symmetric(LedoitWolf().fit(values).covariance_),
        "OAS": _symmetric(OAS().fit(values).covariance_),
    }


def dcc_covariance(values: np.ndarray) -> tuple[np.ndarray, dict[str, float | str]]:
    """Estimate bounded DCC parameters by deterministic likelihood grid."""
    _validate_matrix(values)
    centered = values - np.mean(values, axis=0)
    variances = np.var(centered, axis=0, ddof=1)
    if np.any(variances <= 1e-12):
        raise DataQualityError("DCC requires non-degenerate marginal series")
    standardized = centered / np.sqrt(variances)
    unconditional = np.corrcoef(standardized, rowvar=False)
    best: tuple[float, float, float, np.ndarray] | None = None
    for alpha in (0.01, 0.03, 0.05, 0.08, 0.12):
        for beta in (0.70, 0.80, 0.88, 0.93, 0.96):
            if alpha + beta >= 0.995:
                continue
            objective, state = _dcc_objective(standardized, unconditional, alpha, beta)
            candidate = (objective, alpha, beta, state)
            if best is None or objective < best[0]:
                best = candidate
    if best is None:
        raise DataQualityError("DCC parameter search found no stationary candidate")
    objective, alpha, beta, state = best
    diagonal = np.sqrt(np.maximum(np.diag(state), 1e-12))
    correlation = _symmetric(state / np.outer(diagonal, diagonal))
    covariance = correlation * np.outer(np.sqrt(variances), np.sqrt(variances))
    return _symmetric(covariance), {
        "method": "DCC_GRID_MLE", "alpha": alpha, "beta": beta,
        "persistence": alpha + beta, "negative_log_likelihood": objective,
    }


def _dcc_objective(standardized, unconditional, alpha, beta):
    state = unconditional.copy()
    objective = 0.0
    for row in standardized:
        state = (1.0 - alpha - beta) * unconditional + alpha * np.outer(row, row) + beta * state
        diagonal = np.sqrt(np.maximum(np.diag(state), 1e-12))
        correlation = _symmetric(state / np.outer(diagonal, diagonal))
        sign, logdet = np.linalg.slogdet(correlation)
        if sign <= 0:
            return float("inf"), state
        inverse = np.linalg.pinv(correlation)
        objective += float(logdet + row @ inverse @ row)
    return objective, state


def network_dependence(values: np.ndarray, entities: tuple[str, ...], top_k: int = 2) -> dict[str, Any]:
    _validate_matrix(values)
    if len(entities) != values.shape[1]:
        raise DataQualityError("network entities must align with matrix columns")
    correlation = np.corrcoef(values, rowvar=False)
    if not np.all(np.isfinite(correlation)):
        raise DataQualityError("network correlation contains non-finite values")
    np.fill_diagonal(correlation, 0.0)
    selected = _top_edges(correlation, top_k)
    edges = [
        {"source": entities[left], "target": entities[right], "weight": weight}
        for (left, right), weight in sorted(selected.items())
    ]
    components = _components(entities, edges)
    degree = defaultdict(float)
    for edge in edges:
        degree[edge["source"]] += abs(float(edge["weight"]))
        degree[edge["target"]] += abs(float(edge["weight"]))
    total = max(sum(degree.values()), 1e-12)
    centrality = {entity: float(degree[entity] / total) for entity in entities}
    off_diagonal = correlation[~np.eye(len(entities), dtype=bool)]
    return {
        "entities": entities, "edges": edges, "connected_components": components,
        "weighted_degree_centrality": centrality,
        "mean_absolute_connectedness": float(np.mean(np.abs(off_diagonal))),
        "concentration": float(max(centrality.values(), default=0.0)),
    }


def _top_edges(correlation: np.ndarray, top_k: int) -> dict[tuple[int, int], float]:
    selected: dict[tuple[int, int], float] = {}
    for index in range(len(correlation)):
        count = min(max(top_k, 1), len(correlation) - 1)
        neighbors = np.argsort(np.abs(correlation[index]))[-count:]
        for neighbor in neighbors:
            left, right = sorted((index, int(neighbor)))
            if left != right:
                selected[(left, right)] = float(correlation[left, right])
    return selected


def _components(entities: tuple[str, ...], edges: list[dict[str, Any]]) -> list[list[str]]:
    adjacency: dict[str, set[str]] = {entity: set() for entity in entities}
    for edge in edges:
        adjacency[str(edge["source"])].add(str(edge["target"]))
        adjacency[str(edge["target"])].add(str(edge["source"]))
    remaining, output = set(entities), []
    while remaining:
        start = min(remaining)
        queue, component = deque([start]), []
        remaining.remove(start)
        while queue:
            node = queue.popleft()
            component.append(node)
            for neighbor in sorted(adjacency[node]):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        output.append(component)
    return output


def validate_covariance(
    matrix: np.ndarray, *, repair: bool = True, max_condition: float = 1e8,
    max_repair_ratio: float = 0.50,
) -> tuple[np.ndarray, dict[str, Any]]:
    original = _symmetric(matrix)
    if original.shape[0] < 2 or np.any(np.diag(original) <= 0.0):
        raise NumericalError("covariance requires two entities and positive diagonal")
    eigenvalues, eigenvectors = np.linalg.eigh(original)
    maximum = max(float(eigenvalues[-1]), 1e-12)
    floor = max(maximum / max_condition, 1e-12)
    needs_repair = bool(eigenvalues[0] < floor)
    repaired, repair_ratio = original, 0.0
    if needs_repair:
        if not repair:
            raise NumericalError("covariance is singular, indefinite or ill-conditioned")
        repaired = _symmetric((eigenvectors * np.maximum(eigenvalues, floor)) @ eigenvectors.T)
        denominator = max(float(np.linalg.norm(original, ord="fro")), 1e-12)
        repair_ratio = float(np.linalg.norm(repaired - original, ord="fro") / denominator)
        if repair_ratio > max_repair_ratio:
            raise NumericalError(f"covariance repair ratio {repair_ratio:.4f} exceeds limit")
    values = np.linalg.eigvalsh(repaired)
    minimum, maximum = float(values[0]), float(values[-1])
    condition = float(maximum / max(minimum, 1e-18))
    if condition > max_condition * 1.0001:
        raise NumericalError(f"covariance condition number {condition:.3e} exceeds limit")
    positive = np.maximum(values, 0.0)
    probabilities = positive[positive > 0.0] / max(float(positive.sum()), 1e-12)
    effective_rank = float(np.exp(-np.sum(probabilities * np.log(probabilities))))
    return repaired, {
        "minimum_eigenvalue": minimum, "maximum_eigenvalue": maximum,
        "condition_number": condition, "condition_limit": max_condition,
        "effective_rank": effective_rank, "repair_applied": needs_repair,
        "repair_ratio": repair_ratio, "validated": True,
    }



def covariance_holdout_score(values: np.ndarray, covariance: np.ndarray) -> float:
    """Gaussian negative log score on a chronological holdout."""
    _validate_matrix(values)
    matrix, diagnostics = validate_covariance(covariance, repair=True, max_repair_ratio=0.10)
    cut = min(max(20, int(round(len(values) * 0.80))), len(values) - 5)
    holdout = values[cut:] - np.mean(values[:cut], axis=0)
    inverse = np.linalg.pinv(matrix)
    sign, logdet = np.linalg.slogdet(matrix)
    if sign <= 0:
        raise NumericalError("covariance holdout score requires a positive determinant")
    quadratic = np.einsum("ij,jk,ik->i", holdout, inverse, holdout)
    return float(np.mean(logdet + quadratic) + 1e-6 * diagnostics["condition_number"])


def covariance_to_correlation(matrix: np.ndarray) -> np.ndarray:
    value, _ = validate_covariance(matrix, repair=True, max_repair_ratio=0.10)
    diagonal = np.sqrt(np.maximum(np.diag(value), 1e-12))
    return _symmetric(value / np.outer(diagonal, diagonal))


def dependence_stability(values: np.ndarray, covariance: np.ndarray) -> dict[str, float]:
    """Compare early and late correlation states without future leakage."""
    _validate_matrix(values)
    split = max(8, len(values) // 2)
    early = covariance_to_correlation(sample_covariance(values[:split]))
    late = covariance_to_correlation(sample_covariance(values[split:]))
    candidate = covariance_to_correlation(covariance)
    return {
        "early_late_frobenius": float(np.linalg.norm(late - early, ord="fro")),
        "candidate_late_frobenius": float(np.linalg.norm(candidate - late, ord="fro")),
    }

def _validate_matrix(values: np.ndarray) -> None:
    if values.ndim != 2 or values.shape[0] < 2 or values.shape[1] < 2:
        raise DataQualityError("dependence estimation requires a multivariate sample")
    if not np.all(np.isfinite(values)):
        raise DataQualityError("dependence sample contains non-finite values")


def _symmetric(matrix: np.ndarray) -> np.ndarray:
    value = np.asarray(matrix, dtype=float)
    if value.ndim != 2 or value.shape[0] != value.shape[1]:
        raise NumericalError("matrix must be square")
    if not np.all(np.isfinite(value)):
        raise NumericalError("matrix contains non-finite values")
    return (value + value.T) / 2.0
