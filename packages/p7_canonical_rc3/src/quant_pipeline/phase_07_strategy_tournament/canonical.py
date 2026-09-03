from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

PIPELINE_VERSION = "P7-2.3"
DEFAULT_SCHEMA_VERSION = "2.3.1"


def normalize_json(value: Any) -> Any:
    """Return a deterministic, finite, UTC-normalized JSON value."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, datetime):
        return _utc_datetime(value)
    if isinstance(value, Mapping):
        return {
            str(key): normalize_json(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [normalize_json(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite number is forbidden")
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        normalize_json(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def utc_iso(value: str | datetime) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    return _utc_datetime(parsed)


def build_canonical_artifact(
    *,
    name: str,
    records: Sequence[Mapping[str, Any]],
    module_id: str,
    run_id: str,
    cycle_id: str,
    decision_time: str,
    available_at: str,
    created_at: str,
    lineage_id: str,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
) -> dict[str, Any]:
    normalized_records = [normalize_json(dict(record)) for record in records]
    payload = {
        "artifact_name": name,
        "schema_version": schema_version,
        "pipeline_version": PIPELINE_VERSION,
        "producer_phase": "P7",
        "producer_module_id": module_id,
        "run_id": run_id,
        "cycle_id": cycle_id,
        "decision_time": utc_iso(decision_time),
        "available_at": utc_iso(available_at),
        "lineage_id": lineage_id,
        "records": normalized_records,
    }
    content_hash = digest(payload)
    return {
        "artifact_id": f"{name}:{content_hash[:24]}",
        **payload,
        "created_at": utc_iso(created_at),
        "content_sha256": content_hash,
        "record_count": len(normalized_records),
    }


def _utc_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
