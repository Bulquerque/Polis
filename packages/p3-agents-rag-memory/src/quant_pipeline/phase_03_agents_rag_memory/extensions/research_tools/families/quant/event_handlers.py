"""Handlers for event windows and explicit scenario shocks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from pydantic import JsonValue

from .data_access import query_market_bars, query_records
from .event_window import event_time_from_records, event_window_metrics
from .model_base import OutcomeStatus, QuantCallContext, QuantMode
from .models import EventWindowRequest, QuantOperationResult, ScenarioShockRequest
from .outcomes import build_quant_result
from .ports import PitResearchQueryPort
from .scenario import scenario_value
from .series import MarketBar


def _event_query_bounds(event_time: Any, request: EventWindowRequest, context: QuantCallContext) -> tuple[Any, Any]:
    start = event_time.replace(hour=0, minute=0, second=0, microsecond=0)
    start_time = start - timedelta(days=max(30, request.pre_window * 7 + 7))
    end_time = min(context.decision_time, start + timedelta(days=max(30, request.post_window * 7 + 7)))
    return start_time, end_time


async def _query_benchmark(
    port: PitResearchQueryPort,
    request: EventWindowRequest,
    context: QuantCallContext,
    *,
    start_time: Any,
    end_time: Any,
    qualification_mode: bool = False,
) -> tuple[tuple[MarketBar, ...], tuple[dict[str, JsonValue], ...], int, int]:
    if not request.benchmark_id:
        return (), (), 0, 0
    return await query_market_bars(
        port,
        view_id=request.benchmark_view_id,
        instrument_id=request.benchmark_id,
        start_time=start_time,
        end_time=end_time,
        decision_time=context.decision_time,
        qualification_mode=qualification_mode,
    )


def _placebo_results(
    bars: tuple[MarketBar, ...],
    benchmark_bars: tuple[MarketBar, ...],
    event_time: Any,
    request: EventWindowRequest,
) -> list[dict[str, Any]]:
    if request.research_mode is not QuantMode.STABILITY:
        return []
    anchor_index = next(index for index, bar in enumerate(bars) if bar.observation_time >= event_time)
    results: list[dict[str, Any]] = []
    for offset in request.placebo_offsets:
        candidate = anchor_index + offset
        if candidate < 0 or candidate >= len(bars):
            continue
        metrics, _ = event_window_metrics(
            bars=bars,
            event_time=bars[candidate].observation_time,
            pre_window=request.pre_window,
            post_window=request.post_window,
            return_kind=request.return_kind,
            adjustment=request.adjustment,
            benchmark_bars=benchmark_bars,
        )
        results.append({"offset": offset, **metrics})
    return results


@dataclass(frozen=True, slots=True)
class EventWindowHandler:
    query_port: PitResearchQueryPort

    async def execute(self, request: EventWindowRequest, context: QuantCallContext) -> QuantOperationResult:
        event_records, event_rejected, event_requested = await query_records(
            self.query_port,
            view_id=request.event_view_id,
            filters={"event_id": request.event_id},
            decision_time=context.decision_time,
            qualification_mode=context.qualification_mode,
        )
        event_time, event_record = event_time_from_records(event_records, event_id=request.event_id)
        start_time, end_time = _event_query_bounds(event_time, request, context)
        bars, market_records, market_rejected, market_requested = await query_market_bars(
            self.query_port,
            view_id=request.market_view_id,
            instrument_id=request.instrument_id,
            start_time=start_time,
            end_time=end_time,
            decision_time=context.decision_time,
            qualification_mode=context.qualification_mode,
        )
        benchmark_bars, benchmark_records, benchmark_rejected, benchmark_requested = await _query_benchmark(
            self.query_port,
            request,
            context,
            start_time=start_time,
            end_time=end_time,
            qualification_mode=context.qualification_mode,
        )
        metrics, path = event_window_metrics(
            bars=bars,
            event_time=event_time,
            pre_window=request.pre_window,
            post_window=request.post_window,
            return_kind=request.return_kind,
            adjustment=request.adjustment,
            benchmark_bars=benchmark_bars,
        )
        metrics["placebo_results"] = _placebo_results(bars, benchmark_bars, event_time, request)
        evidence = (event_record, *market_records, *benchmark_records)
        return build_quant_result(
            operation_id="event_window",
            requested_mode=request.research_mode,
            executed_mode=request.research_mode,
            method_id="event_window.observation_index.v1",
            metrics=metrics,
            series=path,
            evidence_records=evidence,
            observations_requested=event_requested + market_requested + benchmark_requested,
            observations_used=len(evidence),
            rejected_future=event_rejected + market_rejected + benchmark_rejected,
            diagnostics=("event_study_is_descriptive_not_causal",),
        )


@dataclass(frozen=True, slots=True)
class ScenarioShockHandler:
    async def execute(self, request: ScenarioShockRequest, context: QuantCallContext) -> QuantOperationResult:
        del context
        base_value, contributions = scenario_value(
            baseline_value=request.baseline_value,
            factor_shocks=request.factor_shocks,
            linear_exposures=request.linear_exposures,
            quadratic_exposures=request.quadratic_exposures,
        )
        metrics: dict[str, Any] = {
            "scenario_id": request.scenario_id,
            "baseline_value": request.baseline_value,
            "scenario_value": base_value,
            "scenario_change": base_value - request.baseline_value,
            "contributions": contributions,
            "probability_assigned": False,
        }
        if request.research_mode in {QuantMode.ROBUST, QuantMode.STABILITY}:
            metrics["sensitivity_grid"] = [
                {
                    "multiplier": multiplier,
                    "scenario_value": scenario_value(
                        baseline_value=request.baseline_value,
                        factor_shocks=request.factor_shocks,
                        linear_exposures=request.linear_exposures,
                        quadratic_exposures=request.quadratic_exposures,
                        multiplier=multiplier,
                    )[0],
                }
                for multiplier in request.sensitivity_multipliers
            ]
        return build_quant_result(
            operation_id="scenario_shock",
            requested_mode=request.research_mode,
            executed_mode=request.research_mode,
            method_id="scenario.explicit_linear_quadratic.v1",
            metrics=metrics,
            evidence_records=(),
            observations_requested=len(request.factor_shocks),
            observations_used=len(request.factor_shocks),
            rejected_future=0,
            outcome_status=OutcomeStatus.PASS,
            diagnostics=("conditional_scenario_not_forecast", "no_probability_assigned"),
        )
