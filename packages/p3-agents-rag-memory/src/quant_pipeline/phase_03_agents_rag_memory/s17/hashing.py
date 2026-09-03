from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Mapping

from pydantic import BaseModel


def _canonicalize(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="python"))
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Naive datetime cannot be canonicalized")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, tuple | list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, set | frozenset):
        canonical_items = [_canonicalize(item) for item in value]
        return sorted(canonical_items, key=lambda item: json.dumps(item, sort_keys=True))
    return value


def canonical_json_bytes(value: object) -> bytes:
    """Serialize a value deterministically for hashing and replay."""

    return json.dumps(
        _canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def stable_id(prefix: str, *parts: object) -> str:
    digest = sha256_hex(list(parts))
    return f"{prefix}:{digest[:32]}"


def lineage_hash(*lineage_ids: str) -> str:
    return stable_id("lin", *sorted(lineage_ids))
