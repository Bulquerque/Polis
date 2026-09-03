from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

import pytest
from pydantic import JsonValue

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.models import (
    QuantMode,
    ReturnStatisticsRequest,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.return_handlers import (
    ReturnStatisticsHandler,
)

from ._fixtures import END, START, InMemoryQueryPort, MARKET_ROWS, context


class ReversedQueryPort(InMemoryQueryPort):
    async def query(
        self,
        *,
        view_id: str,
        filters: Mapping[str, JsonValue],
        decision_time: datetime,
    ) -> Sequence[Mapping[str, JsonValue]]:
        rows = await super().query(view_id=view_id, filters=filters, decision_time=decision_time)
        return tuple(reversed(rows))


@pytest.mark.asyncio
async def test_input_order_does_not_change_result_hash() -> None:
    request = ReturnStatisticsRequest(
        instrument_id="A",
        start_time=START,
        end_time=END,
        research_mode=QuantMode.ROBUST,
    )
    normal = await ReturnStatisticsHandler(InMemoryQueryPort()).execute(request, context())
    reversed_result = await ReturnStatisticsHandler(ReversedQueryPort()).execute(request, context())
    assert normal.result_hash == reversed_result.result_hash


@pytest.mark.asyncio
async def test_future_record_added_does_not_change_historical_metrics() -> None:
    without_future = tuple(row for row in MARKET_ROWS if row.get("record_id") != "A-future")
    request = ReturnStatisticsRequest(instrument_id="A", start_time=START, end_time=END)
    base = await ReturnStatisticsHandler(InMemoryQueryPort({"market_prices": without_future})).execute(request, context())
    with_future = await ReturnStatisticsHandler(InMemoryQueryPort()).execute(request, context())
    assert base.metrics == with_future.metrics
    assert with_future.coverage.observations_rejected_future == 1


def test_no_forbidden_output_field_names_in_contract() -> None:
    forbidden = {"signal", "recommendation", "portfolio_weight", "best_window", "model_selected"}
    from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.models import QuantOperationResult
    schema_text = str(QuantOperationResult.model_json_schema()).lower()
    assert not any(name in schema_text for name in forbidden)
