"""Deterministic identifiers and temporal parsing."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from ..errors import DataQualityError

_HORIZON = re.compile(r"^(?P<count>[1-9]\d*)(?P<unit>[HDWM])$")


def stable_hash(*values: Any) -> str:
    """Return a full deterministic SHA-256 for JSON-compatible lineage inputs."""
    raw = json.dumps(values, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def stable_id(*values: Any, length: int = 24) -> str:
    return stable_hash(*values)[:length]


def as_utc(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def iso_utc(value: str | datetime) -> str:
    return as_utc(value).isoformat().replace("+00:00", "Z")


def horizon_delta(horizon: str) -> timedelta:
    match = _HORIZON.fullmatch(str(horizon).strip().upper())
    if match is None:
        raise DataQualityError(f"unsupported horizon format: {horizon!r}")
    count = int(match.group("count"))
    unit = match.group("unit")
    if unit == "H":
        return timedelta(hours=count)
    if unit == "D":
        return timedelta(days=count)
    if unit == "W":
        return timedelta(weeks=count)
    return timedelta(days=30 * count)
