from __future__ import annotations

import numpy as np

from .contracts import S5State
from .models import (
    HierarchicalBootstrapRequest,
    HierarchicalBootstrapResult,
    ReplicateCovarianceDiagnostic,
)
from .numerics import to_float_matrix

MODULE_ID = "P9.S5.M04"


def _covariance_matrix(matrix: np.ndarray) -> np.ndarray:
    if matrix.shape[1] == 1:
        return np.asarray([[float(np.var(matrix[:, 0], ddof=1))]], dtype=np.float64)
    return np.asarray(np.cov(matrix, rowvar=False, ddof=1), dtype=np.float64)


def _build_replicate_diagnostics(
    request: HierarchicalBootstrapRequest,
    matrix: np.ndarray,
    original_covariance: np.ndarray,
    original_norm: float,
) -> tuple[ReplicateCovarianceDiagnostic, ...]:
    original_regimes = set(request.series.regime_ids or ())
    record_count = min(
        request.indices.replicate_count,
        request.policy.record_replicate_diagnostics,
    )
    diagnostics: list[ReplicateCovarianceDiagnostic] = []
    for replicate_number, row in enumerate(request.indices.indices[:record_count], start=1):
        index = np.asarray(row, dtype=np.int64)
        sampled_covariance = _covariance_matrix(matrix[index])
        covariance_distance = float(
            np.linalg.norm(sampled_covariance - original_covariance, ord="fro")
            / original_norm
        )
        regime_coverage: float | None = None
        if request.series.regime_ids is not None and original_regimes:
            sampled_regimes = {request.series.regime_ids[item] for item in index}
            regime_coverage = len(sampled_regimes) / len(original_regimes)
        diagnostics.append(
            ReplicateCovarianceDiagnostic(
                replicate_id=replicate_number,
                covariance_distance=covariance_distance,
                regime_coverage=regime_coverage,
            )
        )
    return tuple(diagnostics)


def _qualification_findings(
    request: HierarchicalBootstrapRequest,
    average_distance: float,
    minimum_coverage: float | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    limitations: list[str] = []
    reason_codes: list[str] = []
    if average_distance > request.policy.covariance_distance_warning:
        limitations.append("bootstrap covariance differs materially from the observed covariance")
        reason_codes.append("P9_BOOTSTRAP_COVARIANCE_PRESERVATION_WEAK")
    if minimum_coverage is not None and minimum_coverage < request.policy.minimum_regime_coverage:
        limitations.append("some bootstrap replicates have low regime coverage")
        reason_codes.append("P9_BOOTSTRAP_REGIME_COVERAGE_LOW")
    return tuple(reason_codes), tuple(limitations)


def evaluate_hierarchical_bootstrap(
    request: HierarchicalBootstrapRequest,
) -> HierarchicalBootstrapResult:
    """Verify joint time resampling and quantify covariance/regime preservation."""

    matrix = to_float_matrix(request.series.values)
    if request.indices.observation_count != matrix.shape[0]:
        return HierarchicalBootstrapResult(
            status=S5State.INVALID_INPUT,
            original_covariance=(),
            diagnostics=(),
            average_covariance_distance=0.0,
            minimum_regime_coverage=None,
            joint_resampling_verified=False,
            reason_codes=("P9_BOOTSTRAP_INDEX_PANEL_LENGTH_MISMATCH",),
        )
    original_covariance = _covariance_matrix(matrix)
    original_norm = max(
        float(np.linalg.norm(original_covariance, ord="fro")),
        np.finfo(np.float64).eps,
    )
    diagnostics = _build_replicate_diagnostics(
        request,
        matrix,
        original_covariance,
        original_norm,
    )
    distances = [item.covariance_distance for item in diagnostics]
    regime_coverages = [
        item.regime_coverage
        for item in diagnostics
        if item.regime_coverage is not None
    ]
    average_distance = float(np.mean(distances)) if distances else 0.0
    minimum_coverage = min(regime_coverages) if regime_coverages else None
    reason_codes, limitations = _qualification_findings(
        request,
        average_distance,
        minimum_coverage,
    )
    status = S5State.SUCCESS if not limitations else S5State.QUALIFIED_WITH_LIMITATIONS
    return HierarchicalBootstrapResult(
        status=status,
        original_covariance=tuple(
            tuple(float(value) for value in row) for row in original_covariance
        ),
        diagnostics=diagnostics,
        average_covariance_distance=average_distance,
        minimum_regime_coverage=minimum_coverage,
        joint_resampling_verified=True,
        reason_codes=reason_codes,
        limitations=limitations,
    )
