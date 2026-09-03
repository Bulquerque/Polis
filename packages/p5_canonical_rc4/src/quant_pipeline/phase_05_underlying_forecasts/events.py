"""In-memory structured observability for deterministic runs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Event:
    run_id: str
    cycle_id: str
    module_id: str
    event_type: str
    status: str
    details: dict[str, Any]


@dataclass(slots=True)
class EventRecorder:
    events: list[Event] = field(default_factory=list)

    def emit(
        self,
        *,
        run_id: str,
        cycle_id: str,
        module_id: str,
        event_type: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(Event(
            run_id=run_id,
            cycle_id=cycle_id,
            module_id=module_id,
            event_type=event_type,
            status=status,
            details=details or {},
        ))
