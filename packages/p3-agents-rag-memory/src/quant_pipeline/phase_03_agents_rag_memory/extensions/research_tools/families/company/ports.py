"""Point-in-time query contract for P3.S38."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol

from pydantic import JsonValue

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import utc


class PitResearchQueryPort(Protocol):
    async def query(
        self, *, view_id: str, filters: Mapping[str, JsonValue], decision_time: datetime
    ) -> Sequence[Mapping[str, JsonValue]]: ...


class CompanyDataError(ValueError):
    """Raised for explicit company-data contract violations."""


class TemporalVisibilityError(CompanyDataError):
    """Raised when temporal metadata is missing or malformed."""


def parse_datetime(value: JsonValue, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return utc(value)
    if not isinstance(value, str):
        raise TemporalVisibilityError(f"{field_name} must be an ISO datetime")
    try:
        return utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as exc:
        raise TemporalVisibilityError(f"invalid {field_name}: {value}") from exc


def enforce_visibility(records, *, decision_time: datetime):
    cutoff = utc(decision_time)
    visible, rejected = [], 0
    for item in records:
        if "available_at" not in item:
            raise TemporalVisibilityError("record is missing available_at")
        if parse_datetime(item["available_at"], field_name="available_at") > cutoff:
            rejected += 1
            continue
        visible.append(dict(item))
    return tuple(visible), rejected
