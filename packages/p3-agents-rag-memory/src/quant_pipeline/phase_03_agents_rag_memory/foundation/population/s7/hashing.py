"""Versioned deterministic serialization, identifiers and seeds for P3.S7.

The upstream S6 hash helper is retained exactly for S6 artifact verification.
New P3.S7 identifiers use a typed, quantized canonical form to avoid hidden
ordering and floating-point representation dependencies.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN
from enum import Enum
import hashlib
import json
import math
from typing import Any

from pydantic import BaseModel

from .errors import IntegrityError


def upstream_canonical_json_bytes(value: Any) -> bytes:
    """Exact serializer used by P3.S6 v3 artifacts."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def upstream_sha256_hex(value: Any) -> str:
    raw = value if isinstance(value, bytes) else upstream_canonical_json_bytes(value)
    return hashlib.sha256(raw).hexdigest()


def _decimal_text(value: float, digits: int) -> str:
    if not math.isfinite(value):
        raise IntegrityError("P3_S7_NON_FINITE_FLOAT_FORBIDDEN")
    if value == 0.0 and math.copysign(1.0, value) < 0:
        raise IntegrityError("P3_S7_NEGATIVE_ZERO_FORBIDDEN")
    quantum = Decimal(1).scaleb(-digits)
    result = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_EVEN).normalize()
    text = format(result, "f")
    return "0" if text in {"-0", "0E-12", "-0E-12"} else text


def typed_canonical_form(value: Any, *, float_digits: int = 12) -> Any:
    """Convert supported values into a type-preserving deterministic JSON form."""
    if isinstance(value, BaseModel):
        return typed_canonical_form(value.model_dump(mode="json"), float_digits=float_digits)
    if isinstance(value, Enum):
        return typed_canonical_form(value.value, float_digits=float_digits)
    if isinstance(value, dict):
        return {
            str(key): typed_canonical_form(item, float_digits=float_digits)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [typed_canonical_form(item, float_digits=float_digits) for item in value]
    if isinstance(value, float):
        return {"$float": _decimal_text(value, float_digits)}
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    raise IntegrityError(f"P3_S7_UNSUPPORTED_CANONICAL_TYPE:{type(value).__name__}")


def canonical_json_bytes(value: Any, *, float_digits: int = 12) -> bytes:
    canonical = typed_canonical_form(value, float_digits=float_digits)
    return json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(value: Any, *, float_digits: int = 12) -> str:
    raw = value if isinstance(value, bytes) else canonical_json_bytes(value, float_digits=float_digits)
    return hashlib.sha256(raw).hexdigest()


def stable_id(prefix: str, value: Any, *, float_digits: int = 12) -> str:
    return f"{prefix}_{sha256_hex(value, float_digits=float_digits)[:24]}"


def stable_uint63(value: Any, *, float_digits: int = 12) -> int:
    digest = hashlib.sha256(canonical_json_bytes(value, float_digits=float_digits)).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)
