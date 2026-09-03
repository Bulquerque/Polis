"""Shared deterministic helpers for P3.S25."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

from .errors import S25ContractError, S25TemporalError

LOGGER = logging.getLogger("quant_pipeline.phase_03_agents_rag_memory.s25")


def canonical_value(value: Any) -> Any:
    """Convert supported values into a deterministic JSON-compatible form."""
    if isinstance(value, BaseModel):
        return canonical_value(value.model_dump(mode="json", exclude_none=True))
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise S25TemporalError("naive datetime cannot be canonicalized")
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
            raise S25ContractError("non-finite float is forbidden")
        return round(value, 12)
    return value


def canonical_json(value: Any) -> str:
    """Serialize a value with stable ordering and separators."""
    return json.dumps(
        canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def content_hash(value: Any) -> str:
    """Return the SHA-256 of the canonical JSON representation."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def derived_id(prefix: str, *parts: object) -> str:
    """Create a stable identifier from semantically relevant parts."""
    digest = content_hash([str(part) for part in parts])[:24]
    return f"{prefix}_{digest}"


def clamp(value: float, lower: float, upper: float) -> float:
    """Clamp a number without hiding invalid bounds."""
    if lower > upper:
        raise S25ContractError("invalid clamp bounds")
    return max(lower, min(upper, value))


def require_same_context(*artifacts: Any) -> tuple[str, int, datetime]:
    """Require all artifacts to share run, cycle and as-of identity."""
    if not artifacts:
        raise S25ContractError("at least one artifact is required")
    first = artifacts[0]
    expected = (first.run_id, first.cycle_id, first.as_of_time)
    for artifact in artifacts[1:]:
        actual = (artifact.run_id, artifact.cycle_id, artifact.as_of_time)
        if actual != expected:
            raise S25ContractError(
                "cross-artifact context mismatch: "
                f"expected={expected!r}, actual={actual!r}"
            )
    return expected


def require_not_future(moment: datetime, *, as_of: datetime, label: str) -> None:
    """Reject information not available at the run's point in time."""
    if moment > as_of:
        raise S25TemporalError(f"{label} occurs after as_of_time")


def require_effective_cycle(
    effective_cycle: int,
    *,
    current_cycle: int,
    label: str,
) -> None:
    """Reject same-run use of information intended for a later cycle."""
    if effective_cycle > current_cycle:
        raise S25TemporalError(f"{label} is effective only in a future cycle")


def lineage_id(module_id: str, output_name: str, lineages: Iterable[str]) -> str:
    """Derive an output lineage identifier from all declared inputs."""
    normalized = tuple(sorted(set(lineages)))
    if not normalized or any(not item for item in normalized):
        raise S25ContractError("all outputs require non-empty input lineage")
    return derived_id("lin", module_id, output_name, *normalized)


def log_event(
    event: str,
    *,
    module_id: str,
    run_id: str | None = None,
    cycle_id: int | None = None,
    status: str | None = None,
    **dimensions: object,
) -> None:
    """Emit a structured log event through the standard logging API."""
    extra = {
        "event": event,
        "module_id": module_id,
        "run_id": run_id,
        "cycle_id": cycle_id,
        "status": status,
        **dimensions,
    }
    LOGGER.info(event, extra={"p3": extra})
