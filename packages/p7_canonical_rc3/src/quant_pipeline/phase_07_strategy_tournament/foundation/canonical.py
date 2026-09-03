"""Deterministic JSON normalization and hashing for artifact identity."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pydantic import JsonValue

from pydantic import BaseModel


def normalize_json(value: object) -> JsonValue:
    if isinstance(value, BaseModel):
        return normalize_json(value.model_dump(mode="json", exclude_none=False))
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("naive datetime cannot be canonicalized")
        utc_value = value.astimezone(timezone.utc)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float cannot be canonicalized")
        return value
    if isinstance(value, dict):
        return {str(key): normalize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_json(item) for item in value]
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def canonical_json_bytes(value: object) -> bytes:
    normalized = normalize_json(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def content_sha256(value: object) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()
