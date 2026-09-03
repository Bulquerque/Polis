from __future__ import annotations
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from .canonical import parse_aware_datetime
from .errors import S2ContractError
from .models import ExecutionProfile

@dataclass(frozen=True, slots=True)
class TemporalCoordinates:
    event_time: datetime | None
    effective_time: datetime | None
    available_at: datetime | None
    ingested_at: datetime | None

_EFFECTIVE_SOURCES={
 "clean_context_source_panel":(),
 "clean_document_panel":("effective_time","reference_date"),
 "clean_event_reference_panel":("effective_time","event_time","reference_date"),
}

def _date_or_datetime(raw: Any, field: str) -> datetime | None:
    if raw in (None,""): return None
    text=str(raw)
    if len(text)==10: text += "T00:00:00Z"
    return parse_aware_datetime(text,field=field)

def coordinates(row: dict[str,Any], artifact: dict[str,Any], artifact_name: str, profile: ExecutionProfile) -> TemporalCoordinates:
    available=_date_or_datetime(row.get("available_at",artifact.get("available_at")),"available_at")
    ingested=_date_or_datetime(row.get("ingested_at",artifact.get("ingested_at")),"ingested_at")
    event=_date_or_datetime(row.get("event_time"),"event_time")
    effective=None
    for key in _EFFECTIVE_SOURCES.get(artifact_name,()):
        effective=_date_or_datetime(row.get(key),key)
        if effective is not None: break
    if artifact_name=="clean_document_panel" and ingested is None:
        raise S2ContractError("P3_S2_M01_INGESTED_AT_MISSING","clean_document_panel requires ingested_at")
    if profile is ExecutionProfile.QUALIFICATION and artifact_name=="clean_event_reference_panel" and effective is None:
        raise S2ContractError("P3_S2_M01_EFFECTIVE_TIME_MISSING","event records require event/effective/reference time in qualification")
    if available is not None and ingested is not None and ingested < available:
        raise S2ContractError("P3_S2_M01_INGESTED_BEFORE_AVAILABLE",artifact_name)
    return TemporalCoordinates(event,effective,available,ingested)

def canonical_as_of(config: dict[str,Any]) -> Any:
    legacy=config.get("as_of"); canonical=config.get("as_of_time")
    if canonical in (None,"") and legacy in (None,""):
        raise S2ContractError("P3_S2_M01_AS_OF_MISSING","evaluation_window_config.as_of_time is required")
    if canonical not in (None,"") and legacy not in (None,""):
        a=parse_aware_datetime(canonical,field="as_of_time"); b=parse_aware_datetime(legacy,field="as_of")
        if a!=b: raise S2ContractError("P3_S2_M01_AS_OF_ALIAS_MISMATCH","as_of and as_of_time differ")
    return canonical if canonical not in (None,"") else legacy
