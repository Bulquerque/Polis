from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


def _normalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_normalize(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_normalize(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def artifact_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = value.model_dump(mode="python") if isinstance(value, BaseModel) else dict(value)
    data.pop("artifact_id", None)
    data.pop("content_hash", None)
    return data


def compute_artifact_hash(value: BaseModel | dict[str, Any]) -> str:
    return content_hash(artifact_payload(value))


def redact_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
