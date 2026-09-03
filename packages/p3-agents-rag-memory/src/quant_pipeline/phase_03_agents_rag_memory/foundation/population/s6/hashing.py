"""Canonical serialization and content-addressed identifiers."""
from __future__ import annotations
import hashlib
import json
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON-compatible data with a stable byte representation."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    raw = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(raw).hexdigest()


def stable_short_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{sha256_hex(value)[:24]}"
