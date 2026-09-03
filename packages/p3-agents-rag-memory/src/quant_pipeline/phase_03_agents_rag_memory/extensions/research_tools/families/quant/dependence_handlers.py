"""Handlers for correlation and entropy diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .data_access import query_market_bars
from .dependence import correlation_value, pearson_correlation, spearman_correlation
from .entropy import bin_sensitivity_candidates, discretize, permutation_entropy, shannon_entropy
from .model_base import EntropyMethod, OutcomeStatus, QuantCallContext, QuantMode
from .models import CorrelationRequest, EntropyRequest, QuantOperationResult
from .outcomes import build_quant_result
from .ports import PitResearchQueryPort, QuantDataError
from .resampling import bootstrap_interval, paired_moving_block_resamples
from .series import align_returns, compute_returns, quantile


def _correlation_metrics(
    pairs: list[tuple[float, float]],
    request: CorrelationRequest,
    context: QuantCallContext,
) -> tuple[dict[str, Any], OutcomeStatus, tuple[str, ...], tuple[str, ...]]:
    metrics: dict[str, Any] = {"aligned_observations": len(pairs)}
    diagnostics: list[str] = ["alignment_policy=INNER_ON_OBSERVATION_TIME"]
    if len(pairs) < request.min_observations:
        return metrics, OutcomeStatus.DEGRADED, ("P3RT-DATA-CORRELATION-SAMPLE-INSUFFICIENT",), tuple(diagnostics)
    left = [pair[0] for pair in pairs]
    right = [pair[1] for pair in pairs]
    try:
        metrics[request.method.value.lower()] = correlation_value(request.method, left, right)
        if request.research_mode in {QuantMode.ROBUST, QuantMode.STABILITY}:
            metrics["pearson"] = pearson_correlation(left, right)
            metrics["spearman"] = spearman_correlation(left, right)
        _add_correlation_bootstrap(metrics, pairs, request, context)
        return metrics, OutcomeStatus.PASS, (), tuple(diagnostics)
    except QuantDataError as exc:
        diagnostics.append(str(exc))
        return metrics, OutcomeStatus.DEGRADED, ("P3RT-DATA-CORRELATION-UNDEFINED",), tuple(diagnostics)


def _add_correlation_bootstrap(
    metrics: dict[str, Any],
    pairs: list[tuple[float, float]],
    request: CorrelationRequest,
    context: QuantCallContext,
) -> None:
    if request.research_mode is not QuantMode.STABILITY or request.bootstrap_samples <= 0:
        return
    estimates = [
        correlation_value(
            request.method,
            [pair[0] for pair in sample],
            [pair[1] for pair in sample],
        )
        for sample in paired_moving_block_resamples(
            pairs,
            samples=request.bootstrap_samples,
            block_length=request.block_length,
            seed=context.deterministic_seed,
        )
    ]
    alpha = 1.0 - request.bootstrap_confidence
    metrics["bootstrap_interval"] = {
        "lower": quantile(estimates, alpha / 2.0),
        "upper": quantile(estimates, 1.0 - alpha / 2.0),
        "confidence": request.bootstrap_confidence,
        "samples": request.bootstrap_samples,
        "block_length": request.block_length,
    }


def _shannon_metrics(values: list[float], request: EntropyRequest) -> tuple[dict[str, Any], Any]:
    labels, edges = discretize(
        values,
        policy=request.binning_policy,
        bins=request.bins,
        fixed_edges=request.fixed_edges,
    )
    metrics: dict[str, Any] = {
        "shannon_entropy": shannon_entropy(labels, normalize=request.normalize),
        "bin_edges": list(edges),
        "occupied_bins": len(set(labels)),
    }
    if request.research_mode in {QuantMode.ROBUST, QuantMode.STABILITY}:
        metrics["bin_sensitivity"] = {
            str(bins): shannon_entropy(
                discretize(
                    values,
                    policy=request.binning_policy,
                    bins=bins,
                    fixed_edges=request.fixed_edges,
                )[0],
                normalize=request.normalize,
            )
            for bins in bin_sensitivity_candidates(request.bins)
        }
    statistic = lambda sample: shannon_entropy(
        discretize(
            sample,
            policy=request.binning_policy,
            bins=request.bins,
            fixed_edges=request.fixed_edges,
        )[0],
        normalize=request.normalize,
    )
    return metrics, statistic


def _permutation_metrics(values: list[float], request: EntropyRequest) -> tuple[dict[str, Any], Any]:
    value, pattern_count, tie_windows = permutation_entropy(
        values,
        embedding_dimension=request.embedding_dimension,
        delay=request.delay,
        normalize=request.normalize,
    )
    metrics: dict[str, Any] = {
        "permutation_entropy": value,
        "observed_pattern_count": pattern_count,
        "tie_window_count": tie_windows,
    }
    statistic = lambda sample: permutation_entropy(
        sample,
        embedding_dimension=request.embedding_dimension,
        delay=request.delay,
        normalize=request.normalize,
    )[0]
    return metrics, statistic


def _entropy_metrics(
    values: list[float],
    request: EntropyRequest,
    context: QuantCallContext,
) -> tuple[dict[str, Any], OutcomeStatus, tuple[str, ...], tuple[str, ...]]:
    metrics: dict[str, Any] = {"input_observations": len(values)}
    diagnostics: list[str] = []
    try:
        if request.method is EntropyMethod.SHANNON:
            calculated, statistic = _shannon_metrics(values, request)
        else:
            calculated, statistic = _permutation_metrics(values, request)
            diagnostics.append("ties_resolved_by_stable_index_order")
        metrics.update(calculated)
        if request.research_mode is QuantMode.STABILITY and request.bootstrap_samples > 0:
            interval = bootstrap_interval(
                values,
                statistic=statistic,
                samples=request.bootstrap_samples,
                confidence=request.bootstrap_confidence,
                block_length=request.block_length,
                seed=context.deterministic_seed,
            )
            if interval:
                metrics["bootstrap_interval"] = {
                    "lower": interval[0],
                    "upper": interval[1],
                    "confidence": request.bootstrap_confidence,
                    "samples": request.bootstrap_samples,
                    "block_length": request.block_length,
                }
        return metrics, OutcomeStatus.PASS, (), tuple(diagnostics)
    except QuantDataError as exc:
        diagnostics.append(str(exc))
        return metrics, OutcomeStatus.DEGRADED, ("P3RT-DATA-ENTROPY-SAMPLE-INVALID",), tuple(diagnostics)


@dataclass(frozen=True, slots=True)
class CorrelationHandler:
    query_port: PitResearchQueryPort

    async def execute(self, request: CorrelationRequest, context: QuantCallContext) -> QuantOperationResult:
        left_bars, left_records, left_rejected, left_requested = await query_market_bars(
            self.query_port,
            view_id=request.view_id,
            instrument_id=request.left_instrument_id,
            start_time=request.start_time,
            end_time=request.end_time,
            decision_time=context.decision_time,
            qualification_mode=context.qualification_mode,
        )
        right_bars, right_records, right_rejected, right_requested = await query_market_bars(
            self.query_port,
            view_id=request.view_id,
            instrument_id=request.right_instrument_id,
            start_time=request.start_time,
            end_time=request.end_time,
            decision_time=context.decision_time,
            qualification_mode=context.qualification_mode,
        )
        aligned = align_returns(
            compute_returns(left_bars, request.return_kind),
            compute_returns(right_bars, request.return_kind),
        )
        pairs = [(left, right) for _, left, right in aligned]
        metrics, outcome, reason_codes, diagnostics = _correlation_metrics(pairs, request, context)
        return build_quant_result(
            operation_id="correlation",
            requested_mode=request.research_mode,
            executed_mode=request.research_mode,
            method_id=f"dependence.{request.method.value.lower()}.v1",
            metrics=metrics,
            evidence_records=(*left_records, *right_records),
            observations_requested=left_requested + right_requested,
            observations_used=len(aligned) * 2,
            rejected_future=left_rejected + right_rejected,
            outcome_status=outcome,
            reason_codes=reason_codes,
            diagnostics=diagnostics,
        )


@dataclass(frozen=True, slots=True)
class EntropyHandler:
    query_port: PitResearchQueryPort

    async def execute(self, request: EntropyRequest, context: QuantCallContext) -> QuantOperationResult:
        bars, records, rejected, requested = await query_market_bars(
            self.query_port,
            view_id=request.view_id,
            instrument_id=request.instrument_id,
            start_time=request.start_time,
            end_time=request.end_time,
            decision_time=context.decision_time,
            qualification_mode=context.qualification_mode,
        )
        values = [point.value for point in compute_returns(bars, request.input_return_kind)]
        metrics, outcome, reason_codes, diagnostics = _entropy_metrics(values, request, context)
        return build_quant_result(
            operation_id="entropy",
            requested_mode=request.research_mode,
            executed_mode=request.research_mode,
            method_id=f"entropy.{request.method.value.lower()}.v1",
            metrics=metrics,
            evidence_records=records,
            observations_requested=requested,
            observations_used=len(values),
            rejected_future=rejected,
            outcome_status=outcome,
            reason_codes=reason_codes,
            diagnostics=diagnostics,
        )
