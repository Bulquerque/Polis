from __future__ import annotations

from typing import Any

from quant_pipeline.phase_08_contracts.canonical import (
    CanonicalizationError,
    canonical_json_bytes as _canonical_json_bytes,
    canonical_sha256 as _canonical_sha256,
    to_canonical_data as _to_canonical_data,
)

from .errors import ContractIntegrityError

CANONICALIZATION_VERSION = "p8-json-c14n-v2"


def _translate_canonical_error(exc: CanonicalizationError) -> ContractIntegrityError:
    """Preserve the public foundation error contract over the shared kernel."""

    return ContractIntegrityError(str(exc))


def canonicalize(value: Any) -> Any:
    try:
        return _to_canonical_data(value)
    except CanonicalizationError as exc:
        raise _translate_canonical_error(exc) from exc


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return _canonical_json_bytes(value)
    except CanonicalizationError as exc:
        raise _translate_canonical_error(exc) from exc


def content_sha256(value: Any) -> str:
    try:
        return _canonical_sha256(value)
    except CanonicalizationError as exc:
        raise _translate_canonical_error(exc) from exc


def deterministic_id(prefix: str, *parts: Any) -> str:
    digest = content_sha256(list(parts))[:24]
    return f"{prefix}-{digest}"
