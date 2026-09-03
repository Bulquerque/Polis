from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import canonical_json, content_hash


def parse_datetime(value: object, *, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day, tzinfo=UTC)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"{field} is empty")
        if len(text) == 10:
            parsed = datetime.fromisoformat(text).replace(tzinfo=UTC)
        else:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    else:
        raise ValueError(f"{field} is not a supported datetime")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def parse_date(value: object, *, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        return date.fromisoformat(value.strip()[:10])
    raise ValueError(f"{field} is not a supported date")


def optional_float(
    value: object,
    *,
    field: str,
    nonnegative: bool = False,
    positive: bool = False,
) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field}: {value!r}") from exc
    if nonnegative and number < 0:
        raise ValueError(f"{field} must be non-negative")
    if positive and number <= 0:
        raise ValueError(f"{field} must be positive")
    return number


def artifact_records(value: object) -> tuple[Mapping[str, object], ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        records = value.get("records")
        if records is None and isinstance(value.get("outputs"), Mapping):
            outputs = value["outputs"]
            if len(outputs) == 1:
                records = next(iter(outputs.values())).get("records")  # type: ignore[union-attr]
        if records is None:
            return ()
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        records = value
    else:
        return ()
    output: list[Mapping[str, object]] = []
    for row in records:  # type: ignore[assignment]
        if not isinstance(row, Mapping):
            raise ValueError("artifact records must be mappings")
        output.append(dict(row))
    return tuple(output)


def artifact_identity(name: str, value: object) -> tuple[str, str, str]:
    artifact_id = name
    schema_version = "unknown"
    explicit_hash: str | None = None
    if isinstance(value, Mapping):
        artifact_id = str(value.get("artifact_id") or value.get("id") or name)
        schema_version = str(value.get("schema_version") or value.get("pipeline_version") or "unknown")
        raw_hash = value.get("content_hash") or value.get("artifact_hash")
        if isinstance(raw_hash, str) and len(raw_hash) == 64:
            explicit_hash = raw_hash.lower()
    records = artifact_records(value)
    return artifact_id, schema_version, explicit_hash or content_hash(records)


def row_hash(row: Mapping[str, object]) -> str:
    return content_hash(dict(row))


def normalized_token(value: object) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def stable_id(prefix: str, *parts: object) -> str:
    return f"{prefix}_{content_hash(parts)[:24]}"


def canonical_row_key(row: Mapping[str, object], fields: tuple[str, ...]) -> str:
    return canonical_json(tuple(row.get(field) for field in fields))
