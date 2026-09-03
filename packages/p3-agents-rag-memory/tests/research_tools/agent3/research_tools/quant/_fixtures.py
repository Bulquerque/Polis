from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from pydantic import JsonValue

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.models import QuantCallContext

DT = datetime(2024, 1, 10, tzinfo=UTC)
START = datetime(2024, 1, 1, tzinfo=UTC)
END = datetime(2024, 1, 9, tzinfo=UTC)


def record(
    record_id: str,
    *,
    available_at: str,
    source_quality: float = 0.95,
    **fields: JsonValue,
) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "record_id": record_id,
        "source_id": "fixture-source",
        "artifact_id": "fixture-artifact",
        "available_at": available_at,
        "source_quality": source_quality,
        **fields,
    }
    payload["content_hash"] = content_hash(payload)
    return payload


def bars(instrument_id: str, closes: Sequence[float], *, complete_ohlc: bool = True) -> tuple[dict[str, JsonValue], ...]:
    rows = []
    previous = closes[0]
    for index, close in enumerate(closes, start=1):
        day = f"2024-01-{index:02d}T16:00:00Z"
        fields: dict[str, JsonValue] = {
            "instrument_id": instrument_id,
            "observation_time": day,
            "close": close,
        }
        if complete_ohlc:
            open_value = previous
            fields.update(
                {
                    "open": open_value,
                    "high": max(open_value, close) * 1.01,
                    "low": min(open_value, close) * 0.99,
                }
            )
        rows.append(record(f"{instrument_id}-{index}", available_at=day, **fields))
        previous = close
    return tuple(rows)


MARKET_ROWS = (
    *bars("A", (100.0, 110.0, 105.0, 120.0, 90.0, 120.0)),
    *bars("B", (50.0, 55.0, 52.5, 60.0, 45.0, 60.0)),
    *bars("C", (100.0, 100.0, 100.0, 100.0, 100.0, 100.0)),
    record(
        "A-future",
        available_at="2024-01-11T16:00:00Z",
        instrument_id="A",
        observation_time="2024-01-07T16:00:00Z",
        open=120.0,
        high=141.0,
        low=119.0,
        close=140.0,
    ),
)

EVENT_ROWS = (
    record(
        "event-1",
        available_at="2024-01-03T12:00:00Z",
        event_id="E1",
        event_time="2024-01-03T12:00:00Z",
        event_type="EARNINGS",
    ),
    record(
        "event-future",
        available_at="2024-01-12T12:00:00Z",
        event_id="E2",
        event_time="2024-01-09T12:00:00Z",
        event_type="ANNOUNCEMENT",
    ),
)


class InMemoryQueryPort:
    def __init__(self, views: Mapping[str, Sequence[Mapping[str, JsonValue]]] | None = None) -> None:
        self._views = {
            "market_prices": MARKET_ROWS,
            "events": EVENT_ROWS,
            **(views or {}),
        }

    async def query(
        self,
        *,
        view_id: str,
        filters: Mapping[str, JsonValue],
        decision_time: datetime,
    ) -> Sequence[Mapping[str, JsonValue]]:
        del decision_time
        rows = self._views.get(view_id, ())
        instrument_id = filters.get("instrument_id")
        event_id = filters.get("event_id")
        if instrument_id is not None:
            rows = tuple(row for row in rows if row.get("instrument_id") == instrument_id)
        if event_id is not None:
            rows = tuple(row for row in rows if row.get("event_id") == event_id)
        return rows


def context(seed: int = 7, *, qualification_mode: bool = False) -> QuantCallContext:
    return QuantCallContext(
        request_id="request-1",
        person_id="person-1",
        decision_time=DT,
        snapshot_id="snapshot-1",
        deterministic_seed=seed,
        qualification_mode=qualification_mode,
    )
