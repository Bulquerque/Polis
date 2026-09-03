from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel

from .base import NonEmptyStr, Sha256Hex, StrictModel

CANONICALIZATION_VERSION = "P9-C14N-JSON-1"
HASH_ALGORITHM = "sha256"


class IntegrityEnvelope(StrictModel):
    canonicalization_version: NonEmptyStr = CANONICALIZATION_VERSION
    hash_algorithm: NonEmptyStr = HASH_ALGORITHM
    payload_sha256: Sha256Hex


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("non-finite Decimal is not canonicalizable")
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return format(normalized, "f")
    text = format(normalized, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _datetime_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("naive datetime is not canonicalizable")
    utc = value.astimezone(UTC)
    return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")


def to_canonical_data(value: object) -> object:
    """Converts supported domain values into deterministic JSON-compatible data.

    This project profile is inspired by RFC 8785 but deliberately restricts domain
    types: Decimal values are encoded as canonical strings and NaN/Infinity are
    rejected. The profile version is part of every integrity envelope.
    """

    if isinstance(value, BaseModel):
        return to_canonical_data(value.model_dump(mode="python", exclude_none=False))
    if isinstance(value, Enum):
        return to_canonical_data(value.value)
    if isinstance(value, datetime):
        return _datetime_text(value)
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float is not canonicalizable")
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, Mapping):
        output: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical mappings require string keys")
            output[unicodedata.normalize("NFC", key)] = to_canonical_data(item)
        return output
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [to_canonical_data(item) for item in value]
    raise TypeError(f"unsupported canonical type: {type(value)!r}")


def canonical_json_bytes(value: object) -> bytes:
    data = to_canonical_data(value)
    return json.dumps(
        data,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def payload_sha256(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def verify_integrity(payload: object, envelope: IntegrityEnvelope) -> bool:
    if envelope.canonicalization_version != CANONICALIZATION_VERSION:
        return False
    if envelope.hash_algorithm != HASH_ALGORITHM:
        return False
    return payload_sha256(payload) == envelope.payload_sha256
