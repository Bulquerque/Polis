"""Canonical hashing helpers with no hidden state."""
from __future__ import annotations
import hashlib, json
from typing import Any

def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def sha256_hex(value: Any) -> str:
    raw = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(raw).hexdigest()

def stable_short_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{sha256_hex(value)[:24]}"
