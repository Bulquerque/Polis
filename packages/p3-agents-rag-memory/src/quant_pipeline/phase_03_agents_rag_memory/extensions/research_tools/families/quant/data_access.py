"""Defensive view queries used by all quantitative handlers."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from pydantic import JsonValue

from .ports import PitResearchQueryPort, enforce_visibility, parse_datetime
from .series import MarketBar, parse_market_bars


async def query_market_bars(
    port: PitResearchQueryPort,
    *,
    view_id: str,
    instrument_id: str,
    start_time: datetime,
    end_time: datetime,
    decision_time: datetime,
    qualification_mode: bool = False,
) -> tuple[tuple[MarketBar, ...], tuple[dict[str, JsonValue], ...], int, int]:
    raw = await port.query(
        view_id=view_id,
        filters={
            "instrument_id": instrument_id,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        },
        decision_time=decision_time,
    )
    visible, rejected_future = enforce_visibility(
        raw,
        decision_time=decision_time,
        qualification_mode=qualification_mode,
    )
    in_window = tuple(
        record
        for record in visible
        if start_time <= parse_datetime(record.get("observation_time"), field_name="observation_time") <= end_time
        and str(record.get("instrument_id")) == instrument_id
    )
    return parse_market_bars(in_window), in_window, rejected_future, len(raw)


async def query_records(
    port: PitResearchQueryPort,
    *,
    view_id: str,
    filters: Mapping[str, JsonValue],
    decision_time: datetime,
    qualification_mode: bool = False,
) -> tuple[tuple[dict[str, JsonValue], ...], int, int]:
    raw = await port.query(view_id=view_id, filters=filters, decision_time=decision_time)
    visible, rejected_future = enforce_visibility(
        raw,
        decision_time=decision_time,
        qualification_mode=qualification_mode,
    )
    return visible, rejected_future, len(raw)
