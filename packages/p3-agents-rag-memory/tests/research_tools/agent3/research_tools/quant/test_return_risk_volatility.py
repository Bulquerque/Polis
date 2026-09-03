from __future__ import annotations

import math

import pytest

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.models import (
    DrawdownRequest,
    QuantMode,
    RealizedVolatilityRequest,
    ReturnKind,
    ReturnStatisticsRequest,
    VolatilityEstimator,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.return_handlers import (
    DrawdownHandler,
    RealizedVolatilityHandler,
    ReturnStatisticsHandler,
)

from ._fixtures import END, START, InMemoryQueryPort, context


@pytest.mark.asyncio
async def test_return_statistics_simple_and_future_rejection() -> None:
    result = await ReturnStatisticsHandler(InMemoryQueryPort()).execute(
        ReturnStatisticsRequest(
            instrument_id="A",
            start_time=START,
            end_time=END,
            return_kind=ReturnKind.SIMPLE,
            research_mode=QuantMode.ROBUST,
        ),
        context(),
    )
    assert result.outcome_status.value == "PASS"
    assert result.coverage.observations_rejected_future == 1
    assert result.metrics["observation_count"] == 5
    assert "median_absolute_deviation" in result.metrics


@pytest.mark.asyncio
async def test_volatility_estimators_and_seeded_bootstrap_are_deterministic() -> None:
    request = RealizedVolatilityRequest(
        instrument_id="A",
        start_time=START,
        end_time=END,
        research_mode=QuantMode.STABILITY,
        estimators=(
            VolatilityEstimator.CLOSE_TO_CLOSE,
            VolatilityEstimator.PARKINSON,
            VolatilityEstimator.GARMAN_KLASS,
        ),
        bootstrap_samples=40,
        block_length=2,
    )
    handler = RealizedVolatilityHandler(InMemoryQueryPort())
    first = await handler.execute(request, context(19))
    second = await handler.execute(request, context(19))
    assert first.result_hash == second.result_hash
    assert first.metrics["close_to_close"] > 0
    assert first.metrics["parkinson"] > 0
    assert first.metrics["garman_klass"] > 0
    assert "close_to_close_bootstrap_interval" in first.metrics


@pytest.mark.asyncio
async def test_basic_mode_does_not_run_range_estimators() -> None:
    result = await RealizedVolatilityHandler(InMemoryQueryPort()).execute(
        RealizedVolatilityRequest(
            instrument_id="A",
            start_time=START,
            end_time=END,
            research_mode=QuantMode.BASIC,
            estimators=(VolatilityEstimator.PARKINSON,),
        ),
        context(),
    )
    assert result.outcome_status.value == "DEGRADED"
    assert "PARKINSON:MODE_NOT_ALLOWED" in result.diagnostics


@pytest.mark.asyncio
async def test_constant_price_volatility_and_drawdown_are_zero() -> None:
    volatility = await RealizedVolatilityHandler(InMemoryQueryPort()).execute(
        RealizedVolatilityRequest(
            instrument_id="C",
            start_time=START,
            end_time=END,
            estimators=(VolatilityEstimator.CLOSE_TO_CLOSE,),
        ),
        context(),
    )
    drawdown = await DrawdownHandler(InMemoryQueryPort()).execute(
        DrawdownRequest(instrument_id="C", start_time=START, end_time=END),
        context(),
    )
    assert math.isclose(volatility.metrics["close_to_close"], 0.0)
    assert math.isclose(drawdown.metrics["maximum_drawdown"], 0.0)


@pytest.mark.asyncio
async def test_drawdown_known_path() -> None:
    result = await DrawdownHandler(InMemoryQueryPort()).execute(
        DrawdownRequest(instrument_id="A", start_time=START, end_time=END, research_mode=QuantMode.ROBUST),
        context(),
    )
    assert math.isclose(result.metrics["maximum_drawdown"], -0.25)
    assert result.metrics["recovery_time"] == "2024-01-06T16:00:00+00:00"
