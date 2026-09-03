"""Deterministic helpers shared by P3.S26."""
from __future__ import annotations
import hashlib, json, logging
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel
from .errors import S26ContractError, S26TemporalError

LOGGER = logging.getLogger("quant_pipeline.phase_03_agents_rag_memory.s26")

def canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return canonical_value(value.model_dump(mode="json", exclude_none=True))
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise S26TemporalError("naive datetime cannot be canonicalized")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(k): canonical_value(value[k]) for k in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [canonical_value(x) for x in value]
    if isinstance(value, set):
        return sorted(canonical_value(x) for x in value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise S26ContractError("non-finite float is forbidden")
        return round(value, 12)
    return value

def canonical_json(value: Any) -> str:
    return json.dumps(canonical_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()

def derived_id(prefix: str, *parts: object) -> str:
    return f"{prefix}_{content_hash([str(p) for p in parts])[:24]}"

def clamp(value: float, lower: float, upper: float) -> float:
    if lower > upper:
        raise S26ContractError("invalid clamp bounds")
    return max(lower, min(upper, value))

def require_same_context(*artifacts: Any) -> tuple[str, int, datetime]:
    if not artifacts:
        raise S26ContractError("at least one artifact is required")
    expected = (artifacts[0].run_id, artifacts[0].cycle_id, artifacts[0].as_of_time)
    for artifact in artifacts[1:]:
        actual = (artifact.run_id, artifact.cycle_id, artifact.as_of_time)
        if actual != expected:
            raise S26ContractError(f"cross-artifact context mismatch: expected={expected!r}, actual={actual!r}")
    return expected

def require_not_future(moment: datetime, *, as_of: datetime, label: str) -> None:
    if moment > as_of:
        raise S26TemporalError(f"{label} occurs after as_of_time")

def lineage_id(module_id: str, output_name: str, lineages: Iterable[str]) -> str:
    values = tuple(sorted(set(lineages)))
    if not values or any(not x for x in values):
        raise S26ContractError("all outputs require input lineage")
    return derived_id("lin", module_id, output_name, *values)

def log_event(event: str, *, module_id: str, run_id: str | None = None, cycle_id: int | None = None, status: str | None = None, **dims: object) -> None:
    LOGGER.info(event, extra={"p3": {"event": event, "module_id": module_id, "run_id": run_id, "cycle_id": cycle_id, "status": status, **dims}})
