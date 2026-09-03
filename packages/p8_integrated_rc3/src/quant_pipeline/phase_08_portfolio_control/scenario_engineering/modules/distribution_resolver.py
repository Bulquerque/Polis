"""P8.S3.M01 predictive distribution and horizon resolver."""
from __future__ import annotations

import numpy as np

from ..contracts import (
    BeliefRecord, DistributionResolution, DistributionType, PathPayload,
    QuantilePayload, MixturePayload, ParametricPayload, EmpiricalPayload,
)
from ..errors import ContractIntegrityError, NumericalIntegrityError
from ..hashing import canonical_sha256

MODULE_ID = "P8.S3.M01"


def _validate_covariance(matrix: tuple[tuple[float, ...], ...], dimension: int) -> None:
    covariance = np.asarray(matrix, dtype=np.float64)
    if covariance.shape != (dimension, dimension):
        raise ContractIntegrityError("covariance dimension mismatch")
    if not np.all(np.isfinite(covariance)):
        raise NumericalIntegrityError("covariance contains non-finite values")
    if not np.allclose(covariance, covariance.T, atol=1e-10, rtol=0.0):
        raise ContractIntegrityError("covariance must be symmetric")
    if float(np.linalg.eigvalsh(covariance).min()) < -1e-9:
        raise ContractIntegrityError("covariance must be positive semidefinite")


def _validate_payload(belief: BeliefRecord) -> tuple[str, ...]:
    dimension = len(belief.factor_ids)
    payload = belief.payload
    warnings: list[str] = []
    if isinstance(payload, ParametricPayload):
        if len(payload.mean) != dimension:
            raise ContractIntegrityError("parametric mean dimension mismatch")
        _validate_covariance(payload.covariance, dimension)
        if payload.family == "STUDENT_T" and payload.degrees_freedom is None:
            raise ContractIntegrityError("Student-t requires degrees_freedom")
    elif isinstance(payload, MixturePayload):
        total = sum(component.weight for component in payload.components)
        if not np.isclose(total, 1.0, atol=1e-10, rtol=0.0):
            raise ContractIntegrityError("mixture weights must sum to one")
        for component in payload.components:
            if len(component.mean) != dimension:
                raise ContractIntegrityError("mixture mean dimension mismatch")
            _validate_covariance(component.covariance, dimension)
            if component.family == "STUDENT_T" and component.degrees_freedom is None:
                raise ContractIntegrityError("Student-t component requires degrees_freedom")
    elif isinstance(payload, QuantilePayload):
        levels = np.asarray(payload.levels, dtype=np.float64)
        values = np.asarray(payload.values, dtype=np.float64)
        if values.shape != (len(levels), dimension):
            raise ContractIntegrityError("quantile values shape mismatch")
        if np.any(np.diff(levels) <= 0.0) or levels[0] <= 0.0 or levels[-1] >= 1.0:
            raise ContractIntegrityError("quantile levels must be strictly increasing in (0,1)")
        if np.any(np.diff(values, axis=0) < 0.0):
            raise ContractIntegrityError("quantile values must be non-decreasing")
        if payload.gaussian_copula_correlation is None and dimension > 1:
            warnings.append("QUANTILE_DEPENDENCE_UNAVAILABLE_INDEPENDENT_COPULA")
        elif payload.gaussian_copula_correlation is not None:
            _validate_covariance(payload.gaussian_copula_correlation, dimension)
    elif isinstance(payload, EmpiricalPayload):
        samples = np.asarray(payload.samples, dtype=np.float64)
        if samples.ndim != 2 or samples.shape[1] != dimension:
            raise ContractIntegrityError("empirical samples shape mismatch")
        _validate_probabilities(payload.probabilities, samples.shape[0])
    elif isinstance(payload, PathPayload):
        paths = np.asarray(payload.paths, dtype=np.float64)
        if paths.ndim != 3 or paths.shape[2] != dimension:
            raise ContractIntegrityError("path payload shape mismatch")
        if len(payload.step_labels) != paths.shape[1]:
            raise ContractIntegrityError("path step_labels mismatch")
        _validate_probabilities(payload.probabilities, paths.shape[0])
    return tuple(warnings)


def _validate_probabilities(probabilities: tuple[float, ...] | None, count: int) -> None:
    if probabilities is None:
        return
    array = np.asarray(probabilities, dtype=np.float64)
    if array.shape != (count,) or np.any(array < 0.0):
        raise ContractIntegrityError("invalid probability vector")
    if not np.isclose(array.sum(), 1.0, atol=1e-10, rtol=0.0):
        raise ContractIntegrityError("probabilities must sum to one")


def resolve_distribution(belief: BeliefRecord) -> DistributionResolution:
    warnings = _validate_payload(belief)
    path_capability = "FULL_PATH" if belief.distribution_type == DistributionType.PATH else "TERMINAL_ONLY"
    if belief.expiration_horizon is not None and belief.evaluation_horizon == belief.expiration_horizon:
        step_labels = ("EXPIRATION",)
    elif isinstance(belief.payload, PathPayload):
        step_labels = belief.payload.step_labels
    else:
        step_labels = ("EVALUATION_HORIZON",)
    return DistributionResolution(
        distribution_type=belief.distribution_type,
        probability_measure=belief.probability_measure,
        factor_ids=belief.factor_ids,
        step_labels=step_labels,
        path_capability=path_capability,
        content_sha256=canonical_sha256(belief),
        warnings=warnings,
    )
