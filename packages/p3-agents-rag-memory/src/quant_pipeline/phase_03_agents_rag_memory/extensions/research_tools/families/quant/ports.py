"""Process-local data port and defensive point-in-time filtering for P3.S39."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, time
from typing import Protocol

from pydantic import JsonValue

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import utc


class PitResearchQueryPort(Protocol):
    async def query(
        self,
        *,
        view_id: str,
        filters: Mapping[str, JsonValue],
        decision_time: datetime,
    ) -> Sequence[Mapping[str, JsonValue]]:
        """Return records authorized by the P1/P2 research boundary."""


class QuantDataError(ValueError):
    """Raised when a quantitative input violates an explicit data contract."""


class TemporalVisibilityError(QuantDataError):
    """Raised when temporal metadata is missing or malformed."""


class EventWindowNotMatureError(TemporalVisibilityError):
    """Raised when a requested post-event window is not fully observable yet."""


UNPROVEN_PIT_STATUSES = frozenset({
    "DATE_LEVEL_PIT_UNPROVEN",
    "UNPROVEN",
    "SNAPSHOT_ONLY",
    "SNAPSHOT_OR_DATE_LEVEL_ONLY",
})


def _daily_reference_timestamp(value: JsonValue, *, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise TemporalVisibilityError(f"{field_name} must be an ISO date")
    try:
        return datetime.fromisoformat(value[:10]).replace(tzinfo=UTC)
    except ValueError as exc:
        raise TemporalVisibilityError(f"invalid {field_name}: {value}") from exc


def parse_datetime(value: JsonValue, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return utc(value)
    if not isinstance(value, str):
        raise TemporalVisibilityError(f"{field_name} must be an ISO datetime")
    try:
        return utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as exc:
        raise TemporalVisibilityError(f"invalid {field_name}: {value}") from exc


def enforce_visibility(
    records: Sequence[Mapping[str, JsonValue]],
    *,
    decision_time: datetime,
    qualification_mode: bool = False,
) -> tuple[tuple[dict[str, JsonValue], ...], int]:
    cutoff = utc(decision_time)
    visible: list[dict[str, JsonValue]] = []
    rejected = 0
    for record in records:
        if "available_at" not in record:
            raise TemporalVisibilityError("record is missing available_at")
        if qualification_mode:
            pit_status = str(record.get("pit_status", "")).upper()
            if pit_status in UNPROVEN_PIT_STATUSES or "UNPROVEN" in pit_status:
                raise TemporalVisibilityError(
                    f"PIT qualification rejected unproven status: {pit_status or 'MISSING'}"
                )
        available_at = parse_datetime(record["available_at"], field_name="available_at")
        if available_at > cutoff:
            rejected += 1
            continue
        observation_value = None
        observation_field = None
        for candidate in ("observation_time", "event_time", "observed_at"):
            if candidate in record and record[candidate] is not None:
                observation_value = record[candidate]
                observation_field = candidate
                break
        if observation_value is None and record.get("reference_date") is not None:
            observation_value = record["reference_date"]
            observation_field = "reference_date"
        if observation_value is not None:
            observation_time = (
                _daily_reference_timestamp(observation_value, field_name=observation_field)
                if observation_field == "reference_date"
                else parse_datetime(observation_value, field_name=observation_field)
            )
            if observation_time > cutoff:
                rejected += 1
                continue
        visible.append(dict(record))
    return tuple(visible), rejected
