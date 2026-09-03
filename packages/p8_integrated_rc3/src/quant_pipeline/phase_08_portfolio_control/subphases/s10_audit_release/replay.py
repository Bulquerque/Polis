from __future__ import annotations
from collections import defaultdict
from decimal import Decimal
from .models_common import content_sha256
from .models_state import ReplayEvent

_ALLOWED = {"POSITION", "CASH", "VIRTUAL_ALLOCATION", "NOOP"}

def validate_event_sequence(events: tuple[ReplayEvent, ...]) -> bool:
    sequences = [event.sequence for event in events]
    return sequences == sorted(sequences) and len(sequences) == len(set(sequences))

def replay_state(events: tuple[ReplayEvent, ...]) -> dict[str, object]:
    positions: dict[str, Decimal] = defaultdict(Decimal)
    allocations: dict[str, Decimal] = defaultdict(Decimal)
    cash = Decimal("0")
    for event in events:
        if event.event_type not in _ALLOWED:
            raise ValueError(f"unsupported replay event type: {event.event_type}")
        if event.event_type == "POSITION" and event.instrument_id:
            positions[event.instrument_id] += event.quantity_delta
        elif event.event_type == "CASH":
            cash += event.cash_delta
        elif event.event_type == "VIRTUAL_ALLOCATION" and event.instrument_id and event.candidate_id:
            key = f"{event.candidate_id}|{event.instrument_id}"
            allocations[key] += event.quantity_delta
    return {
        "positions": {key: str(value) for key, value in sorted(positions.items())},
        "allocations": {key: str(value) for key, value in sorted(allocations.items())},
        "cash": str(cash),
        "last_sequence": events[-1].sequence if events else -1,
    }

def replay_hash(events: tuple[ReplayEvent, ...]) -> str:
    return content_sha256(replay_state(events))
