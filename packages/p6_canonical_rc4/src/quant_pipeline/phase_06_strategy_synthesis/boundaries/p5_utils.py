"""Small shared helpers for the P5 boundary."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Mapping

from ..foundation.hashing import utc

_HORIZON = re.compile(r"^(?P<count>[1-9]\d*)(?P<unit>[HDWM])$")


def horizon_days(value: str) -> int:
    match = _HORIZON.fullmatch(value.strip().upper())
    if match is None:
        raise ValueError(f"unsupported P5 horizon: {value!r}")
    count = int(match.group("count"))
    unit = match.group("unit")
    if unit == "H":
        if count % 24:
            raise ValueError("sub-day P5 horizons are not supported by P6 candidates")
        return count // 24
    if unit == "D":
        return count
    if unit == "W":
        return 7 * count
    return 30 * count


def as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def normalized(value: Any) -> Any:
    if isinstance(value, datetime):
        return utc(value).isoformat()
    if isinstance(value, str) and ("T" in value or value.endswith("Z")):
        try:
            return utc(as_datetime(value)).isoformat()
        except ValueError:
            return value
    return value


def raw_records(artifact: Mapping[str, Any]) -> list[Any]:
    records = artifact.get("records")
    if isinstance(records, list):
        return records
    nested = artifact.get("artifact")
    if isinstance(nested, Mapping) and isinstance(nested.get("records"), list):
        return list(nested["records"])
    content = artifact.get("content")
    if isinstance(content, Mapping) and isinstance(content.get("records"), list):
        return list(content["records"])
    return []
