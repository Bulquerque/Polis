"""Small point-in-time queries shared by company handlers."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pydantic import JsonValue

from .ports import PitResearchQueryPort, enforce_visibility


def view_declared(port: PitResearchQueryPort, view_id: str) -> bool:
    """Return whether the local manifest declares a view, including an empty one."""
    declared = getattr(port, "available_view_ids", ())
    return view_id in declared


async def query_company_records(
    port: PitResearchQueryPort, *, view_id: str, entity_id: str, decision_time: datetime,
    extra_filters: Mapping[str, JsonValue] | None = None,
):
    filters: dict[str, JsonValue] = {"entity_id": entity_id}
    if extra_filters:
        filters.update(extra_filters)
    raw = await port.query(view_id=view_id, filters=filters, decision_time=decision_time)
    return enforce_visibility(raw, decision_time=decision_time)
