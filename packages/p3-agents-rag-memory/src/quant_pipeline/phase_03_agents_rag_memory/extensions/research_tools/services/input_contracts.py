"""Explicit extraction helpers for heterogeneous P1/P2 artifact envelopes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timezone
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel

from ..core.hashing import content_hash

_RECORD_KEYS = (
    "records",
    "rows",
    "items",
    "artifacts",
    "snapshots",
    "sources",
    "documents",
    "quotes",
    "data",
)


def python_value(value: object) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    return value


def as_mapping(value: object, label: str) -> Mapping[str, Any]:
    raw = python_value(value)
    if not isinstance(raw, Mapping):
        raise TypeError(f"{label} must be a mapping or Pydantic model")
    return raw


def as_records(value: object | None) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    raw = python_value(value)
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        return tuple(item for item in raw if isinstance(item, Mapping))
    if not isinstance(raw, Mapping):
        return ()
    for key in _RECORD_KEYS:
        candidate = raw.get(key)
        if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes, bytearray)):
            return tuple(item for item in candidate if isinstance(item, Mapping))
    return (raw,)


def first_value(record: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def as_nonempty_str(value: Any, fallback: str) -> str:
    if value in (None, ""):
        return fallback
    return str(value).strip() or fallback


def parse_datetime(value: Any, *, date_timezone: timezone = timezone.utc) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("naive datetime is forbidden")
        return value.astimezone(timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=date_timezone).astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        parsed_date = date.fromisoformat(text)
        return datetime.combine(parsed_date, time.min, tzinfo=date_timezone).astimezone(timezone.utc)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("naive datetime string is forbidden")
    return parsed.astimezone(timezone.utc)


def unique_strings(records: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> tuple[str, ...]:
    values: set[str] = set()
    for record in records:
        value = first_value(record, keys)
        if value not in (None, ""):
            values.add(str(value))
    return tuple(sorted(values))


def safe_storage_token(value: Any, *, raw_artifact_id: str, snapshot_id: str) -> str:
    text = "" if value in (None, "") else str(value)
    path = PurePosixPath(text.replace("\\", "/"))
    if ".." in path.parts:
        raise ValueError("storage reference contains traversal segments")
    return content_hash({"raw_artifact_id": raw_artifact_id, "snapshot_id": snapshot_id, "storage_ref": text})


def metadata_without_payload(value: object) -> dict[str, Any]:
    raw = python_value(value)
    if not isinstance(raw, Mapping):
        return {"value_type": type(raw).__name__}
    blocked = set(_RECORD_KEYS) | {"payload", "content", "bytes", "text"}
    safe: dict[str, Any] = {}
    for key, item in raw.items():
        if key in blocked:
            continue
        if isinstance(item, Mapping):
            safe[str(key)] = {
                str(inner_key): inner_value
                for inner_key, inner_value in item.items()
                if inner_key not in blocked and not isinstance(inner_value, (list, tuple, dict))
            }
        elif not isinstance(item, (list, tuple, set, dict, bytes, bytearray)):
            safe[str(key)] = item
    return safe


def require_no_hidden_payload(value: object) -> None:
    forbidden = {"records", "rows", "items", "documents", "quotes", "payload", "content", "bytes", "text"}

    def walk(item: object, path: str) -> None:
        raw = python_value(item)
        if isinstance(raw, Mapping):
            leaked = forbidden.intersection(str(key) for key in raw)
            if leaked:
                raise ValueError(f"hidden payload keys at {path}: {sorted(leaked)}")
            for key, nested in raw.items():
                walk(nested, f"{path}.{key}")
        elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
            for index, nested in enumerate(raw):
                walk(nested, f"{path}[{index}]")

    walk(value, "artifact")
