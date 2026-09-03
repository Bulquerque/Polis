"""Handlers for return statistics, volatility and drawdown."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .data_access import query_market_bars
from .drawdown import drawdown_diagnostics
from .model_base import OutcomeStatus, QuantCallContext, QuantMode, ReturnKind, VolatilityEstimator
from .models import DrawdownRequest, QuantOperationResult, RealizedVolatilityRequest, ReturnStatisticsRequest
from .outcomes import build_quant_result
from .ports import PitResearchQueryPort, QuantDataError
from .resampling import bootstrap_interval
from .returns import return_statistics
from .series import MarketBar, compute_returns, sample_std
from .volatility import estimator_value


def _volatility_metrics(
    bars: tuple[MarketBar, ...],
    request: RealizedVolatilityRequest,
) -> tuple[dict[str, Any], list[str]]:
    metrics: dict[str, Any] = {}
    failed: list[str] = []
    allowed = {VolatilityEstimator.CLOSE_TO_CLOSE}
    if request.research_mode in {QuantMode.ROBUST, QuantMode.STABILITY}:
        allowed.update({VolatilityEstimator.PARKINSON, VolatilityEstimator.GARMAN_KLASS})
    for estimator in request.estimators:
        if estimator not in allowed:
            failed.append(f"{estimator.value}:MODE_NOT_ALLOWED")
            continue
        try:
            metrics[estimator.value.lower()] = estimator_value(estimator, bars, request.annualization_factor)
        except QuantDataError as exc:
            failed.append(f"{estimator.value}:{exc}")
    return metrics, failed


def _fallback_close_to_close(
    bars: tuple[MarketBar, ...],
    request: RealizedVolatilityRequest,
    metrics: dict[str, Any],
    failed: list[str],
) -> tuple[QuantMode, str | None]:
    if metrics or request.research_mode is QuantMode.BASIC:
        return request.research_mode, None
    try:
        metrics["close_to_close"] = estimator_value(
            VolatilityEstimator.CLOSE_TO_CLOSE,
            bars,
            request.annualization_factor,
        )
        return QuantMode.BASIC, "ROBUST_ESTIMATORS_UNAVAILABLE"
    except QuantDataError as exc:
        failed.append(f"CLOSE_TO_CLOSE:{exc}")
        return request.research_mode, None


def _add_volatility_stability(
    bars: tuple[MarketBar, ...],
    request: RealizedVolatilityRequest,
    context: QuantCallContext,
    metrics: dict[str, Any],
    executed_mode: QuantMode,
    downgrade_reason: str | None,
) -> tuple[QuantMode, str | None]:
    if request.research_mode is not QuantMode.STABILITY:
        return executed_mode, downgrade_reason
    returns = [point.value for point in compute_returns(bars, ReturnKind.LOG)]
    if request.bootstrap_samples <= 0 or len(returns) < 2:
        return (QuantMode.ROBUST if metrics else QuantMode.BASIC), "BOOTSTRAP_NOT_REQUESTED_OR_SAMPLE_TOO_SHORT"
    interval = bootstrap_interval(
        returns,
        statistic=lambda sample: sample_std(sample) * request.annualization_factor**0.5,
        samples=request.bootstrap_samples,
        confidence=request.bootstrap_confidence,
        block_length=request.block_length,
        seed=context.deterministic_seed,
    )
    if interval:
        metrics["close_to_close_bootstrap_interval"] = {
            "lower": interval[0],
            "upper": interval[1],
            "confidence": request.bootstrap_confidence,
            "samples": request.bootstrap_samples,
            "block_length": request.block_length,
        }
    return executed_mode, downgrade_reason


def _volatility_status(
    metrics: dict[str, Any],
    failed: list[str],
    downgrade_reason: str | None,
) -> tuple[OutcomeStatus, tuple[str, ...]]:
    if not metrics:
        return OutcomeStatus.DEGRADED, ("P3RT-DATA-VOLATILITY-ESTIMATOR-UNAVAILABLE",)
    if downgrade_reason:
        return OutcomeStatus.DEGRADED, ("P3RT-MODE-DOWNGRADED",)
    if failed:
        return OutcomeStatus.DEGRADED, ("P3RT-DATA-OHLC-INCOMPLETE",)
    return OutcomeStatus.PASS, ()


@dataclass(frozen=True, slots=True)
class ReturnStatisticsHandler:
    query_port: PitResearchQueryPort

    async def execute(self, request: ReturnStatisticsRequest, context: QuantCallContext) -> QuantOperationResult:
        bars, records, rejected, requested = await query_market_bars(
            self.query_port,
            view_id=request.view_id,
            instrument_id=request.instrument_id,
            start_time=request.start_time,
            end_time=request.end_time,
            decision_time=context.decision_time,
            qualification_mode=context.qualification_mode,
        )
        values = [point.value for point in compute_returns(bars, request.return_kind)]
        if not values:
            return build_quant_result(
                operation_id="return_statistics",
                requested_mode=request.research_mode,
                executed_mode=request.research_mode,
                method_id=f"returns.{request.return_kind.value.lower()}.v1",
                metrics={"observation_count": 0},
                evidence_records=records,
                observations_requested=requested,
                observations_used=0,
                rejected_future=rejected,
                outcome_status=OutcomeStatus.EMPTY_VALID,
                reason_codes=("P3RT-DATA-RETURN-SAMPLE-EMPTY",),
            )
        metrics, diagnostics = return_statistics(
            values,
            mode=request.research_mode,
            quantiles=request.quantiles,
            trim_fraction=request.trim_fraction,
            annualization_factor=request.annualization_factor,
        )
        return build_quant_result(
            operation_id="return_statistics",
            requested_mode=request.research_mode,
            executed_mode=request.research_mode,
            method_id=f"returns.{request.return_kind.value.lower()}.v1",
            metrics=metrics,
            evidence_records=records,
            observations_requested=requested,
            observations_used=len(bars),
            rejected_future=rejected,
            diagnostics=diagnostics,
        )


@dataclass(frozen=True, slots=True)
class RealizedVolatilityHandler:
    query_port: PitResearchQueryPort

    async def execute(self, request: RealizedVolatilityRequest, context: QuantCallContext) -> QuantOperationResult:
        bars, records, rejected, requested = await query_market_bars(
            self.query_port,
            view_id=request.view_id,
            instrument_id=request.instrument_id,
            start_time=request.start_time,
            end_time=request.end_time,
            decision_time=context.decision_time,
            qualification_mode=context.qualification_mode,
        )
        metrics, failed = _volatility_metrics(bars, request)
        executed_mode, downgrade_reason = _fallback_close_to_close(bars, request, metrics, failed)
        executed_mode, downgrade_reason = _add_volatility_stability(
            bars,
            request,
            context,
            metrics,
            executed_mode,
            downgrade_reason,
        )
        outcome, reason_codes = _volatility_status(metrics, failed, downgrade_reason)
        return build_quant_result(
            operation_id="realized_volatility",
            requested_mode=request.research_mode,
            executed_mode=executed_mode,
            method_id="volatility.estimator_set.v1",
            metrics=metrics,
            evidence_records=records,
            observations_requested=requested,
            observations_used=len(bars),
            rejected_future=rejected,
            outcome_status=outcome,
            downgrade_reason=downgrade_reason,
            reason_codes=reason_codes,
            diagnostics=sorted(failed),
        )


@dataclass(frozen=True, slots=True)
class DrawdownHandler:
    query_port: PitResearchQueryPort

    async def execute(self, request: DrawdownRequest, context: QuantCallContext) -> QuantOperationResult:
        bars, records, rejected, requested = await query_market_bars(
            self.query_port,
            view_id=request.view_id,
            instrument_id=request.instrument_id,
            start_time=request.start_time,
            end_time=request.end_time,
            decision_time=context.decision_time,
            qualification_mode=context.qualification_mode,
        )
        if not bars:
            return build_quant_result(
                operation_id="drawdown",
                requested_mode=request.research_mode,
                executed_mode=request.research_mode,
                method_id="drawdown.wealth_index.v1",
                metrics={"observation_count": 0},
                evidence_records=records,
                observations_requested=requested,
                observations_used=0,
                rejected_future=rejected,
                outcome_status=OutcomeStatus.EMPTY_VALID,
                reason_codes=("P3RT-DATA-DRAWDOWN-SAMPLE-EMPTY",),
            )
        metrics, path = drawdown_diagnostics(bars, wealth_start=request.wealth_start)
        return build_quant_result(
            operation_id="drawdown",
            requested_mode=request.research_mode,
            executed_mode=request.research_mode,
            method_id="drawdown.wealth_index.v1",
            metrics=metrics,
            series=path,
            evidence_records=records,
            observations_requested=requested,
            observations_used=len(bars),
            rejected_future=rejected,
        )
