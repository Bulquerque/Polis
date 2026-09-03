from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from .errors import CycleIdentityError


def stable_id(prefix: str, *parts: object) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return f"{prefix}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def resolve_cycle_index(cycle_id: str, explicit: int | None = None) -> int:
    if explicit is not None:
        if explicit < 0:
            raise CycleIdentityError("cycle index must be non-negative")
        return explicit
    groups = re.findall(r"\d+", cycle_id)
    if not groups:
        raise CycleIdentityError(
            f"legacy consumer requires an integer cycle index for {cycle_id!r}; pass it explicitly"
        )
    return int(groups[-1])


def parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError(f"expected datetime or ISO-8601 string, got {type(value).__name__}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return parsed.astimezone(timezone.utc)

def canonical_json_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
