from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from ._compat import content_hash
from .types import Frequency, parse_date, parse_datetime


def artifact_records(value: object) -> tuple[dict[str, object], ...]:
    if isinstance(value, Mapping):
        for key in ("records", "items", "rows"):
            rows = value.get(key)
            if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes, bytearray)):
                return tuple(dict(row) for row in rows if isinstance(row, Mapping))
        return ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(dict(row) for row in value if isinstance(row, Mapping))
    return ()


def artifact_identity(name: str, value: object) -> tuple[str, str, str]:
    if isinstance(value, Mapping):
        artifact_id = str(value.get("artifact_id") or value.get("id") or name)
        lineage_id = str(value.get("lineage_id") or f"lineage:{artifact_id}")
        digest = str(value.get("content_hash") or value.get("hash") or content_hash(value))
        return artifact_id, lineage_id, digest
    digest = content_hash(value)
    return name, f"lineage:{name}", digest


def series_id(row: Mapping[str, object]) -> str | None:
    for key in ("series_id", "dataset_id", "indicator_id", "macro_series_id", "symbol"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return None


def observation_date(row: Mapping[str, object]) -> date:
    for key in ("reference_date", "date", "period_end", "period", "observation_date"):
        value = row.get(key)
        if value not in (None, ""):
            return parse_date(value, field=key)
    raise ValueError("macro observation date is missing")


def numeric_value(row: Mapping[str, object]) -> float:
    for key in ("value", "observation_value", "amount", "numeric_value"):
        value = row.get(key)
        if value not in (None, "", ".", "NA", "N/A"):
            return float(value)
    raise ValueError("macro value is missing")


def available_at(row: Mapping[str, object]) -> datetime:
    for key in ("available_at", "declared_available_at", "realtime_start", "published_at"):
        value = row.get(key)
        if value not in (None, ""):
            return parse_datetime(value, field=key)
    raise ValueError("available_at is missing")


def published_at(row: Mapping[str, object]) -> datetime | None:
    for key in ("published_at", "release_timestamp", "release_at"):
        value = row.get(key)
        if value not in (None, ""):
            return parse_datetime(value, field=key)
    return None


def vintage_date(row: Mapping[str, object]) -> date | None:
    for key in ("vintage_date", "realtime_start", "revision_date", "release_date"):
        value = row.get(key)
        if value not in (None, ""):
            return parse_date(value, field=key)
    return None


def revision_id(row: Mapping[str, object]) -> str | None:
    for key in ("revision_id", "source_revision", "vintage_id", "realtime_start"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None



def optional_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    token = str(value).strip().casefold()
    if token in {"true", "1", "yes", "y"}:
        return True
    if token in {"false", "0", "no", "n"}:
        return False
    raise ValueError("boolean value is invalid")

def infer_frequency(value: object) -> Frequency:
    token = str(value or "").strip().upper().replace(" ", "_")
    aliases = {
        "D": Frequency.DAILY,
        "DAILY": Frequency.DAILY,
        "W": Frequency.WEEKLY,
        "WEEKLY": Frequency.WEEKLY,
        "M": Frequency.MONTHLY,
        "MONTHLY": Frequency.MONTHLY,
        "Q": Frequency.QUARTERLY,
        "QUARTERLY": Frequency.QUARTERLY,
        "A": Frequency.ANNUAL,
        "Y": Frequency.ANNUAL,
        "ANNUAL": Frequency.ANNUAL,
        "YEARLY": Frequency.ANNUAL,
        "IRREGULAR": Frequency.IRREGULAR,
    }
    return aliases.get(token, Frequency.UNKNOWN)


def normalize_region(value: object) -> str | None:
    token = str(value or "").strip().upper().replace(" ", "_")
    if token in {"BR", "BRA", "BRAZIL", "BRASIL"}:
        return "BR"
    if token in {"US", "USA", "UNITED_STATES", "UNITED_STATES_OF_AMERICA"}:
        return "US"
    return token or None


def row_sort_key(row: Mapping[str, object]) -> tuple[str, str, str, str]:
    sid = series_id(row) or ""
    try:
        obs = observation_date(row).isoformat()
    except ValueError:
        obs = ""
    try:
        avail = available_at(row).isoformat()
    except ValueError:
        avail = ""
    rev = revision_id(row) or ""
    return sid, obs, avail, rev


def as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
