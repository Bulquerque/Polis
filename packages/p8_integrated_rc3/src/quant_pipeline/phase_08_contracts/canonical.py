"""Canonical serialization and hashing.

The rules are deliberately small and explicit so every phase can reproduce the
same bytes without relying on process-local object representations.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence, Set
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

from pydantic import BaseModel


class CanonicalizationError(ValueError):
    """Raised when a value cannot be represented in the canonical format."""


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise CanonicalizationError("non-finite Decimal values are forbidden")
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _datetime_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CanonicalizationError("naive datetime is forbidden")
    utc_value = value.astimezone(UTC)
    return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def to_canonical_data(value: object, *, exclude_keys: frozenset[str] = frozenset()) -> object:
    """Convert supported values to a JSON-safe deterministic structure."""

    if isinstance(value, BaseModel):
        return to_canonical_data(value.model_dump(mode="python"), exclude_keys=exclude_keys)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return _datetime_text(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError("non-finite float values are forbidden")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        items: dict[str, object] = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str):
                raise CanonicalizationError("mapping keys must be strings")
            if raw_key in exclude_keys:
                continue
            items[raw_key] = to_canonical_data(raw_value, exclude_keys=exclude_keys)
        return {key: items[key] for key in sorted(items)}
    if isinstance(value, Set):
        converted = [to_canonical_data(item, exclude_keys=exclude_keys) for item in value]
        return sorted(converted, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [to_canonical_data(item, exclude_keys=exclude_keys) for item in value]
    raise CanonicalizationError(f"unsupported canonical type: {type(value)!r}")


def canonical_json_bytes(value: object, *, exclude_keys: frozenset[str] = frozenset()) -> bytes:
    data = to_canonical_data(value, exclude_keys=exclude_keys)
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(value: object, *, exclude_keys: frozenset[str] = frozenset()) -> str:
    return hashlib.sha256(canonical_json_bytes(value, exclude_keys=exclude_keys)).hexdigest()


def raw_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def finalize_content_hash[T: BaseModel](model: T, *, field_name: str = "content_sha256") -> T:
    """Return a fully revalidated copy with its canonical embedded hash set."""

    digest = canonical_sha256(model, exclude_keys=frozenset({field_name}))
    payload = model.model_dump(mode="python")
    payload[field_name] = digest
    return type(model).model_validate(payload, strict=True)
