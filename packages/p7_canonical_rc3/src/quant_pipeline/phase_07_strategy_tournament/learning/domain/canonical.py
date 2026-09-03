from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Iterable, Mapping

from .errors import fail


def parse_utc(value: object, *, field: str) -> datetime:
    if not isinstance(value, str):
        fail("P7_LTR_CONTRACT_INVALID", f"{field} must be an ISO timestamp", field=field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("P7_LTR_CONTRACT_INVALID", f"{field} must be an ISO timestamp", field=field)
    if parsed.tzinfo is None:
        fail("P7_LTR_CONTRACT_INVALID", f"{field} must be timezone-aware", field=field)
    return parsed.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize(value: Any) -> Any:
    if isinstance(value, datetime):
        return iso_utc(value)
    if isinstance(value, Mapping):
        return {str(key): _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            fail("P7_LTR_NON_FINITE_VALUE", "wire artifacts cannot contain NaN or infinity")
        return 0.0 if value == 0.0 else value
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sorted_records(records: Iterable[Mapping[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    result = [dict(record) for record in records]
    return sorted(result, key=lambda row: tuple(str(row.get(key, "")) for key in keys))
