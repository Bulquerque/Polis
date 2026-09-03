from __future__ import annotations

import math

import pytest

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.event_handlers import (
    EventWindowHandler,
    ScenarioShockHandler,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.models import (
    EventAdjustment,
    EventWindowRequest,
    QuadraticExposure,
    QuantMode,
    ScenarioShockRequest,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.ports import (
    EventWindowNotMatureError,
    QuantDataError,
)

from ._fixtures import InMemoryQueryPort, context


@pytest.mark.asyncio
async def test_event_window_benchmark_adjustment() -> None:
    result = await EventWindowHandler(InMemoryQueryPort()).execute(
        EventWindowRequest(
            event_id="E1",
            instrument_id="A",
            benchmark_id="B",
            adjustment=EventAdjustment.BENCHMARK,
            pre_window=1,
            post_window=1,
            research_mode=QuantMode.ROBUST,
        ),
        context(),
    )
    assert math.isclose(result.metrics["cumulative_adjusted_return"], 0.0, abs_tol=1e-12)
    assert "event_study_is_descriptive_not_causal" in result.diagnostics


@pytest.mark.asyncio
async def test_future_event_is_not_visible() -> None:
    with pytest.raises(QuantDataError):
        await EventWindowHandler(InMemoryQueryPort()).execute(
            EventWindowRequest(event_id="E2", instrument_id="A", pre_window=0, post_window=0),
            context(),
        )


@pytest.mark.asyncio
async def test_incomplete_event_window_is_rejected() -> None:
    with pytest.raises(EventWindowNotMatureError):
        await EventWindowHandler(InMemoryQueryPort()).execute(
            EventWindowRequest(event_id="E1", instrument_id="A", pre_window=10, post_window=10),
            context(),
        )


@pytest.mark.asyncio
async def test_explicit_scenario_has_analytic_solution_and_no_probability() -> None:
    result = await ScenarioShockHandler().execute(
        ScenarioShockRequest(
            scenario_id="S1",
            research_mode=QuantMode.ROBUST,
            baseline_value=100.0,
            factor_shocks={"rates": 0.01, "fx": -0.05},
            linear_exposures={"rates": -200.0, "fx": 20.0},
            quadratic_exposures=(
                QuadraticExposure(left_factor="rates", right_factor="fx", coefficient=10.0),
            ),
        ),
        context(),
    )
    expected = 100.0 - 2.0 - 1.0 + 10.0 * 0.01 * -0.05
    assert math.isclose(result.metrics["scenario_value"], expected)
    assert result.metrics["probability_assigned"] is False
    assert "sensitivity_grid" in result.metrics
