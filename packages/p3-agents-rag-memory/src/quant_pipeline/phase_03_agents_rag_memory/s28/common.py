"""Deterministic helpers shared by P3.S28."""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

from .errors import S28ContractError, S28TemporalError

LOGGER = logging.getLogger("quant_pipeline.phase_03_agents_rag_memory.s28")


def canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return canonical_value(value.model_dump(mode="json", exclude_none=False))
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise S28TemporalError("naive datetime cannot be canonicalized")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [canonical_value(item) for item in value]
    if isinstance(value, set):
        return sorted(canonical_value(item) for item in value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise S28ContractError("non-finite float is forbidden")
        return round(value, 12)
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(canonical_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def derived_id(prefix: str, *parts: object) -> str:
    return f"{prefix}_{content_hash([str(part) for part in parts])[:24]}"


def require_same_context(*artifacts: Any) -> tuple[str, int, datetime]:
    if not artifacts:
        raise S28ContractError("at least one artifact is required")
    expected = (artifacts[0].run_id, artifacts[0].cycle_id, artifacts[0].as_of_time)
    for artifact in artifacts[1:]:
        actual = (artifact.run_id, artifact.cycle_id, artifact.as_of_time)
        if actual != expected:
            raise S28ContractError(f"cross-artifact context mismatch: expected={expected!r}, actual={actual!r}")
    return expected


def require_not_future(moment: datetime, *, as_of: datetime, label: str) -> None:
    if moment > as_of:
        raise S28TemporalError(f"{label} occurs after as_of_time")


def lineage_id(module_id: str, output_name: str, lineages: Iterable[str]) -> str:
    values = tuple(sorted(set(lineages)))
    if not values or any(not item for item in values):
        raise S28ContractError("all outputs require input lineage")
    return derived_id("lin", module_id, output_name, *values)


def log_event(event: str, *, module_id: str, run_id: str | None = None, cycle_id: int | None = None, status: str | None = None, **dims: object) -> None:
    LOGGER.info(event, extra={"p3": {"event": event, "module_id": module_id, "run_id": run_id, "cycle_id": cycle_id, "status": status, **dims}})
