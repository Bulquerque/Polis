from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from quant_pipeline.phase_08_contracts.canonical import (
    canonical_json_bytes as _canonical_json_bytes,
    canonical_sha256 as _canonical_sha256,
)

from ..errors import HashMismatchError

CANONICALIZATION_VERSION = "p8-json-c14n-v2"


def canonical_json_bytes(value: BaseModel | dict[str, Any]) -> bytes:
    return _canonical_json_bytes(value)


def canonical_sha256(value: BaseModel | dict[str, Any]) -> str:
    return _canonical_sha256(value)


def verify_payload_hash(payload: BaseModel, expected_hash: str) -> None:
    actual = canonical_sha256(payload)
    if actual != expected_hash:
        raise HashMismatchError(f"payload hash mismatch: expected={expected_hash}, actual={actual}")
