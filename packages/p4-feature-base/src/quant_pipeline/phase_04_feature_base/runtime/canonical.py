from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
from typing import Any, Mapping

from .datetime_utils import utc_z


def canonical_value(value: Any) -> Any:
    if is_dataclass(value):
        return canonical_value(asdict(value))
    if isinstance(value, datetime):
        return utc_z(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return canonical_value(value.value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("non-finite floats are forbidden in canonical JSON")
        return value
    if isinstance(value, Mapping):
        return {str(k): canonical_value(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [canonical_value(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        canonical_value(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )


def content_hash(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def p2_legacy_digest(value: Any) -> str:
    blob = json.dumps(value, sort_keys=True, default=str, ensure_ascii=True).encode("utf-8")
    return sha256(blob).hexdigest()


def deterministic_id(prefix: str, value: Any, length: int = 20) -> str:
    return f"{prefix}-{content_hash(value)[:length]}"
