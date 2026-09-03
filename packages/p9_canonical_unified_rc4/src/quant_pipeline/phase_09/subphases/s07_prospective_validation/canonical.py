"""Canonical serialization and integrity helpers.

The payload hash never includes its own integrity envelope. Datetimes are
serialized by Pydantic in UTC and mappings are sorted recursively by JSON.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_core import to_jsonable_python

CANONICALIZATION_VERSION = "JCS-LIKE-JSON-UTF8-V1"


def _normalize(value: Any) -> Any:
    """Normalize non-JSON containers without losing ordered-sequence semantics."""

    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="python", exclude_none=False))
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        normalized = [_normalize(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
            ),
        )
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return to_jsonable_python(value, temporal_mode="iso8601", inf_nan_mode="constants")


def canonical_json_bytes(value: BaseModel | dict[str, Any] | list[Any]) -> bytes:
    """Return deterministic UTF-8 JSON bytes for a validated payload."""

    raw = _normalize(value)
    text = json.dumps(
        raw,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return text.encode("utf-8")


def payload_sha256(value: BaseModel | dict[str, Any] | list[Any]) -> str:
    """Hash a canonical payload."""

    return sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: str | Path) -> str:
    """Hash a file using streaming reads."""

    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
