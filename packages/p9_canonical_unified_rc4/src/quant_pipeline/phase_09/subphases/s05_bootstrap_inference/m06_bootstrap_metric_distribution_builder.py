from __future__ import annotations

import numpy as np

from .contracts import ConfidenceIntervalMethod, S5State
from .metric_registry import MetricCalculatorRegistry, MetricContext, MetricEvaluationError
from .models import MetricDistributionRequest, MetricDistributionResult, MetricEstimate
from .numerics import to_float_matrix

MODULE_ID = "P9.S5.M06"


def _series_column(series_ids: tuple[str, ...], series_id: str | None) -> int | None:
    if series_id is None:
        return None
    try:
        return series_ids.index(series_id)
    except ValueError as error:
        raise ValueError(f"unknown series id: {series_id}") from error


def _context_for_definition(
    matrix: np.ndarray,
    definition,
    series_ids: tuple[str, ...],
    periods_per_year: float,
) -> MetricContext:
    target_column = _series_column(series_ids, definition.target_series_id)
    if target_column is None:
        raise ValueError("target_series_id is required")
    benchmark_column = _series_column(series_ids, definition.benchmark_series_id)
    risk_free_column = _series_column(series_ids, definition.risk_free_series_id)
    return MetricContext(
        returns=np.asarray(matrix[:, target_column], dtype=np.float64),
        periods_per_year=periods_per_year,
        benchmark=(
            np.asarray(matrix[:, benchmark_column], dtype=np.float64)
            if benchmark_column is not None
            else None
        ),
        risk_free=(
            np.asarray(matrix[:, risk_free_column], dtype=np.float64)
            if risk_free_column is not None
            else None
        ),
    )


def _empty_estimate(
    definition,
    replicate_count: int,
    status: S5State,
    reason_code: str,
) -> MetricEstimate:
    return MetricEstimate(
        metric_id=definition.metric_id,
        metric_name=definition.metric_name,
        observed_value=None,
        bootstrap_mean=None,
        bootstrap_median=None,
        standard_error=None,
        confidence_interval_low=None,
        confidence_interval_high=None,
        lower_confidence_bound=None,
        worst_quantile=None,
        probability_above_threshold=None,
        valid_replicates=0,
        invalid_replicates=replicate_count,
        status=status,
        reason_codes=(reason_code,),
    )


def _summarize_distribution(
    values: np.ndarray,
    observed: float,
    definition,
    request: MetricDistributionRequest,
) -> MetricEstimate:
    valid = values[np.isfinite(values)]
    invalid_count = int(values.size - valid.size)
    if valid.size < definition.minimum_valid_replicates:
        return MetricEstimate(
            metric_id=definition.metric_id,
            metric_name=definition.metric_name,
            observed_value=observed,
            bootstrap_mean=None,
            bootstrap_median=None,
            standard_error=None,
            confidence_interval_low=None,
            confidence_interval_high=None,
            lower_confidence_bound=None,
            worst_quantile=None,
            probability_above_threshold=None,
            valid_replicates=int(valid.size),
            invalid_replicates=invalid_count,
            status=S5State.INSUFFICIENT_VALID_REPLICATES,
            reason_codes=("P9_BOOTSTRAP_INSUFFICIENT_VALID_REPLICATES",),
        )
    alpha = 1.0 - request.policy.confidence_level
    lower_quantile = float(np.quantile(valid, alpha / 2.0))
    upper_quantile = float(np.quantile(valid, 1.0 - alpha / 2.0))
    if request.policy.interval_method is ConfidenceIntervalMethod.BASIC:
        low = 2.0 * observed - upper_quantile
        high = 2.0 * observed - lower_quantile
    else:
        low = lower_quantile
        high = upper_quantile
    probability = (
        float(np.mean(valid > definition.threshold))
        if definition.threshold is not None
        else None
    )
    invalid_fraction = invalid_count / values.size if values.size else 1.0
    partial = invalid_fraction > request.policy.invalid_replicate_limit
    return MetricEstimate(
        metric_id=definition.metric_id,
        metric_name=definition.metric_name,
        observed_value=observed,
        bootstrap_mean=float(np.mean(valid)),
        bootstrap_median=float(np.median(valid)),
        standard_error=float(np.std(valid, ddof=1)) if valid.size > 1 else 0.0,
        confidence_interval_low=float(low),
        confidence_interval_high=float(high),
        lower_confidence_bound=float(low),
        worst_quantile=float(np.quantile(valid, request.policy.worst_quantile)),
        probability_above_threshold=probability,
        valid_replicates=int(valid.size),
        invalid_replicates=invalid_count,
        status=S5State.PARTIAL_METRIC_COVERAGE if partial else S5State.SUCCESS,
        reason_codes=("P9_BOOTSTRAP_METRIC_REPLICATE_INVALID",) if partial else (),
    )


def _replicate_metric_values(
    request: MetricDistributionRequest,
    matrix: np.ndarray,
    definition,
    registry: MetricCalculatorRegistry,
) -> np.ndarray:
    values = np.full(request.indices.replicate_count, np.nan, dtype=np.float64)
    for replicate_index, row in enumerate(request.indices.indices):
        sampled = matrix[np.asarray(row, dtype=np.int64)]
        try:
            context = _context_for_definition(
                sampled,
                definition,
                request.series.series_ids,
                request.series.periods_per_year,
            )
            values[replicate_index] = registry.evaluate(context, definition)
        except (MetricEvaluationError, ValueError, FloatingPointError):
            continue
    return values


def _evaluate_definition(
    request: MetricDistributionRequest,
    matrix: np.ndarray,
    definition,
    registry: MetricCalculatorRegistry,
) -> tuple[MetricEstimate, str | None]:
    if definition.metric_version != request.series.metric_registry_version:
        return (
            _empty_estimate(
                definition,
                request.indices.replicate_count,
                S5State.METRIC_VERSION_MISMATCH,
                "P9_BOOTSTRAP_METRIC_VERSION_MISMATCH",
            ),
            None,
        )
    try:
        observed_context = _context_for_definition(
            matrix,
            definition,
            request.series.series_ids,
            request.series.periods_per_year,
        )
        observed = registry.evaluate(observed_context, definition)
    except (MetricEvaluationError, ValueError):
        return (
            _empty_estimate(
                definition,
                request.indices.replicate_count,
                S5State.INSUFFICIENT_EVIDENCE,
                "P9_BOOTSTRAP_METRIC_UNAVAILABLE",
            ),
            f"metric unavailable: {definition.metric_id}",
        )
    replicate_values = _replicate_metric_values(request, matrix, definition, registry)
    return _summarize_distribution(replicate_values, observed, definition, request), None


def _aggregate_status(estimates: list[MetricEstimate]) -> S5State:
    if not estimates:
        return S5State.INVALID_INPUT
    states = {estimate.status for estimate in estimates}
    if states == {S5State.SUCCESS}:
        return S5State.SUCCESS
    if S5State.METRIC_VERSION_MISMATCH in states:
        return S5State.METRIC_VERSION_MISMATCH
    unavailable = {S5State.INSUFFICIENT_EVIDENCE, S5State.INSUFFICIENT_VALID_REPLICATES}
    if all(state in unavailable for state in states):
        return S5State.INSUFFICIENT_EVIDENCE
    return S5State.PARTIAL_METRIC_COVERAGE


def build_metric_distributions(
    request: MetricDistributionRequest,
    registry: MetricCalculatorRegistry | None = None,
) -> MetricDistributionResult:
    """Recompute frozen upstream metrics on every dependent-bootstrap replicate."""

    matrix = to_float_matrix(request.series.values)
    if request.indices.observation_count != matrix.shape[0]:
        return MetricDistributionResult(
            status=S5State.INVALID_INPUT,
            metric_registry_version=request.series.metric_registry_version,
            estimates=(),
            reason_codes=("P9_BOOTSTRAP_INDEX_PANEL_LENGTH_MISMATCH",),
        )
    calculator_registry = registry or MetricCalculatorRegistry()
    estimates: list[MetricEstimate] = []
    limitations: list[str] = []
    for definition in request.metric_definitions:
        estimate, limitation = _evaluate_definition(
            request,
            matrix,
            definition,
            calculator_registry,
        )
        estimates.append(estimate)
        if limitation is not None:
            limitations.append(limitation)
    return MetricDistributionResult(
        status=_aggregate_status(estimates),
        metric_registry_version=request.series.metric_registry_version,
        estimates=tuple(estimates),
        reason_codes=tuple(
            sorted({code for estimate in estimates for code in estimate.reason_codes})
        ),
        limitations=tuple(limitations),
    )
