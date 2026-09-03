
"""Deterministic execution context for S2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class S2ExecutionContext:
    run_id: str
    cycle_id: str
    decision_time: datetime
    computed_at: datetime

    def __post_init__(self) -> None:
        if not self.run_id or not self.cycle_id:
            raise ValueError("run_id and cycle_id must be non-empty")
        for name in ("decision_time", "computed_at"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
            object.__setattr__(self, name, value.astimezone(UTC))
        if self.computed_at < self.decision_time:
            raise ValueError("computed_at must not be before decision_time")
