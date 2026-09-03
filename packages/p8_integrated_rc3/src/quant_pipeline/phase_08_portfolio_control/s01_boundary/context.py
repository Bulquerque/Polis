"""Deterministic execution context supplied by the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from quant_pipeline.phase_08_contracts.enums import RuntimeMode


@dataclass(frozen=True, slots=True)
class S1ExecutionContext:
    run_id: str
    cycle_id: str
    cycle_sequence: int
    decision_time: datetime
    market_cutoff_at: datetime
    computed_at: datetime
    runtime_mode: RuntimeMode

    def __post_init__(self) -> None:
        if not self.run_id or not self.cycle_id:
            raise ValueError("run_id and cycle_id must be non-empty")
        if self.cycle_sequence < 0:
            raise ValueError("cycle_sequence must be non-negative")
        for name in ("decision_time", "market_cutoff_at", "computed_at"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
            object.__setattr__(self, name, value.astimezone(UTC))
        if self.market_cutoff_at > self.decision_time:
            raise ValueError("market_cutoff_at must not be after decision_time")
        if self.computed_at < self.decision_time:
            raise ValueError("computed_at must not be before decision_time")
