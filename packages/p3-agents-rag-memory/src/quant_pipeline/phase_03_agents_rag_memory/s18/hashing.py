from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping, Sequence


def canonical_value(value: Any) -> Any:
    """Convert supported values into a deterministic JSON-compatible form."""

    if hasattr(value, "model_dump"):
        return canonical_value(value.model_dump(mode="python"))
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("cannot hash a naive datetime")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        sorted_items = sorted(value.items(), key=lambda pair: str(pair[0]))
        return {
            str(key): canonical_value(item)
            for key, item in sorted_items
        }
    if isinstance(value, (tuple, list)):
        return [canonical_value(item) for item in value]
    if isinstance(value, set):
        return sorted(canonical_value(item) for item in value)
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def hash_without_field(value: Any, field: str = "content_hash") -> str:
    payload = canonical_value(value)
    if not isinstance(payload, dict):
        raise TypeError("hash_without_field requires a mapping-like value")
    payload.pop(field, None)
    return sha256_hex(payload)


def deterministic_id(prefix: str, *parts: object) -> str:
    digest = sha256_hex(list(parts))[:32]
    return f"{prefix}:{digest}"


def normalized_subject(value: str) -> str:
    return " ".join(value.casefold().split())
