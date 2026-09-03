"""Shared, narrowly scoped utilities for the P7.S1 bounded context."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from copy import deepcopy
from datetime import datetime
import math
from pydantic import JsonValue

from ..canonical import content_sha256


def records_by_key(
    records: Iterable[dict[str, JsonValue]],
    key: str,
) -> dict[str, list[dict[str, JsonValue]]]:
    grouped: dict[str, list[dict[str, JsonValue]]] = defaultdict(list)
    for record in records:
        value = record.get(key)
        if not isinstance(value, str) or not value:
            continue
        grouped[value].append(deepcopy(record))
    return {key: sorted(values, key=content_sha256) for key, values in grouped.items()}


def parse_aware_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError("timestamp must be ISO string or datetime")
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return result


def walk_json(value: JsonValue, path: str = "$"):
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk_json(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk_json(item, f"{path}[{index}]")


def nonfinite_paths(value: JsonValue) -> list[str]:
    return [
        path
        for path, item in walk_json(value)
        if isinstance(item, float) and not math.isfinite(item)
    ]
