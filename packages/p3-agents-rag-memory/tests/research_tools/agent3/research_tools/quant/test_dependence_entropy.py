from __future__ import annotations

import math

import pytest

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.models import (
    BinningPolicy,
    CorrelationMethod,
    CorrelationRequest,
    EntropyMethod,
    EntropyRequest,
    QuantMode,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.dependence_handlers import (
    CorrelationHandler,
    EntropyHandler,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.entropy import (
    permutation_entropy,
    shannon_entropy,
)

from ._fixtures import END, START, InMemoryQueryPort, context


@pytest.mark.asyncio
async def test_identical_return_paths_have_unit_correlations() -> None:
    result = await CorrelationHandler(InMemoryQueryPort()).execute(
        CorrelationRequest(
            left_instrument_id="A",
            right_instrument_id="B",
            start_time=START,
            end_time=END,
            method=CorrelationMethod.SPEARMAN,
            research_mode=QuantMode.ROBUST,
        ),
        context(),
    )
    assert math.isclose(result.metrics["pearson"], 1.0)
    assert math.isclose(result.metrics["spearman"], 1.0)


@pytest.mark.asyncio
async def test_constant_series_correlation_is_explicitly_degraded() -> None:
    result = await CorrelationHandler(InMemoryQueryPort()).execute(
        CorrelationRequest(
            left_instrument_id="A",
            right_instrument_id="C",
            start_time=START,
            end_time=END,
        ),
        context(),
    )
    assert result.outcome_status.value == "DEGRADED"
    assert "P3RT-DATA-CORRELATION-UNDEFINED" in result.reason_codes


def test_shannon_entropy_known_distribution() -> None:
    assert math.isclose(shannon_entropy((0, 0, 1, 1), normalize=True), 1.0)


def test_permutation_entropy_monotone_series_is_zero() -> None:
    value, patterns, ties = permutation_entropy(
        (1.0, 2.0, 3.0, 4.0, 5.0),
        embedding_dimension=3,
        delay=1,
        normalize=True,
    )
    assert math.isclose(value, 0.0)
    assert patterns == 1
    assert ties == 0


@pytest.mark.asyncio
async def test_entropy_stability_is_seeded_and_policy_explicit() -> None:
    request = EntropyRequest(
        instrument_id="A",
        start_time=START,
        end_time=END,
        method=EntropyMethod.SHANNON,
        binning_policy=BinningPolicy.EQUAL_WIDTH,
        bins=4,
        research_mode=QuantMode.STABILITY,
        bootstrap_samples=30,
        block_length=2,
    )
    handler = EntropyHandler(InMemoryQueryPort())
    first = await handler.execute(request, context(23))
    second = await handler.execute(request, context(23))
    assert first.result_hash == second.result_hash
    assert "bin_sensitivity" in first.metrics
    assert "bootstrap_interval" in first.metrics
