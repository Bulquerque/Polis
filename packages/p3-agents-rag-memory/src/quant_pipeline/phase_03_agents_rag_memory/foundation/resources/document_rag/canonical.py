from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from datetime import datetime
from typing import Any

from pydantic import BaseModel

TOKEN_RE = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)


def canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return canonicalize(value.model_dump(mode="json"))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): canonicalize(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [canonicalize(v) for v in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def content_hash(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return "\n".join(line.rstrip() for line in normalized.replace("\r\n", "\n").split("\n")).strip()


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(token.casefold() for token in TOKEN_RE.findall(normalize_text(text)))


def l2_normalize(values: list[float]) -> tuple[float, ...]:
    norm = math.sqrt(sum(v * v for v in values))
    if norm == 0:
        return tuple(values)
    return tuple(v / norm for v in values)
