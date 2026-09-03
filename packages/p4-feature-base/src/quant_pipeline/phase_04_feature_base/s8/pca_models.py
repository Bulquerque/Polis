from __future__ import annotations
from dataclasses import dataclass
import warnings
import numpy as np
from sklearn.decomposition import PCA, SparsePCA
from sklearn.exceptions import ConvergenceWarning

@dataclass(frozen=True)
class LinearFit:
    representation_type: str
    components: np.ndarray
    mean: np.ndarray
    explained_variance_ratio: np.ndarray
    scores: np.ndarray
    reconstructed: np.ndarray
    converged: bool


def canonicalize_signs(components: np.ndarray, scores: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    fixed_components = components.copy()
    fixed_scores = scores.copy()
    for index, row in enumerate(fixed_components):
        pivot = int(np.argmax(np.abs(row)))
        if row[pivot] < 0:
            fixed_components[index] *= -1
            fixed_scores[:, index] *= -1
    return fixed_components, fixed_scores


def select_component_count(train: np.ndarray, threshold: float, maximum: int) -> tuple[PCA, int]:
    upper = max(1, min(maximum, train.shape[1], train.shape[0] - 1))
    full = PCA(n_components=upper, svd_solver="full")
    full.fit(train)
    cumulative = np.cumsum(full.explained_variance_ratio_)
    count = int(np.searchsorted(cumulative, threshold) + 1)
    return full, min(count, upper)


def fit_pca(train: np.ndarray, validation: np.ndarray, threshold: float, maximum: int) -> LinearFit:
    _, count = select_component_count(train, threshold, maximum)
    model = PCA(n_components=count, svd_solver="full")
    model.fit(train)
    scores = model.transform(validation)
    components, scores = canonicalize_signs(model.components_, scores)
    reconstructed = scores @ components + model.mean_
    return LinearFit("PCA", components, model.mean_, model.explained_variance_ratio_, scores, reconstructed, True)


def fit_sparse_pca(train: np.ndarray, validation: np.ndarray, count: int, alpha: float, ridge_alpha: float,
                   max_iter: int, tol: float, random_state: int) -> LinearFit:
    model = SparsePCA(n_components=count, alpha=alpha, ridge_alpha=ridge_alpha, max_iter=max_iter,
        tol=tol, method="lars", random_state=random_state)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        model.fit(train)
    scores = model.transform(validation)
    components, scores = canonicalize_signs(model.components_, scores)
    reconstructed = scores @ components + model.mean_
    converged = not any(issubclass(item.category, ConvergenceWarning) for item in caught)
    return LinearFit("SPARSE_PCA", components, model.mean_, np.array([], dtype=float), scores, reconstructed, converged)
