"""Portable graph record codecs with optional Parquet delegation."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TypeVar

from pydantic import BaseModel

from .adapters.parquet import decode_parquet, encode_parquet
from .canonical import canonical_json_bytes
from .errors import ErrorCategory, PersistenceFailureError, error
from .models import RecordFormat

T = TypeVar("T", bound=BaseModel)


def encode_jsonl(records: Iterable[BaseModel]) -> bytes:
    lines = [canonical_json_bytes(record) for record in records]
    return b"\n".join(lines) + (b"\n" if lines else b"")


def decode_jsonl(content: bytes, model: type[T]) -> tuple[T, ...]:
    if not content.strip():
        return ()
    return tuple(
        model.model_validate_json(line, strict=True)
        for line in content.splitlines()
        if line.strip()
    )


def encode_records(
    records: Sequence[BaseModel],
    record_format: RecordFormat,
) -> tuple[bytes, str, str, str]:
    if record_format == RecordFormat.JSONL:
        return encode_jsonl(records), "application/x-ndjson", ".jsonl", "jsonl.v1"
    if record_format == RecordFormat.PARQUET:
        return (
            encode_parquet(records),
            "application/vnd.apache.parquet",
            ".parquet",
            "parquet.v1",
        )
    raise PersistenceFailureError(
        error(
            "P3_S13_UNSUPPORTED_RECORD_FORMAT",
            ErrorCategory.PERSISTENCE,
            "unsupported graph record format",
            context={"record_format": str(record_format)},
        )
    )


def decode_records(content: bytes, model: type[T], media_type: str) -> tuple[T, ...]:
    if media_type == "application/x-ndjson":
        return decode_jsonl(content, model)
    if media_type == "application/vnd.apache.parquet":
        return decode_parquet(content, model)
    raise PersistenceFailureError(
        error(
            "P3_S13_UNSUPPORTED_MEDIA_TYPE",
            ErrorCategory.PERSISTENCE,
            "unsupported graph record media type",
            context={"media_type": media_type},
        )
    )
