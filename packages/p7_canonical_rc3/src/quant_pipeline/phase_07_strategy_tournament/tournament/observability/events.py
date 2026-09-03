from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from ..boundary.base import TimeAwareModel


class DebugEvent(TimeAwareModel):
    _time_fields = ("timestamp", "decision_time")

    event_name: str
    timestamp: datetime
    trace_id: str | None = None
    run_id: str
    cycle_id: str
    decision_time: datetime | None = None
    module_id: str
    status: str
    reason_code: str | None = None
    input_artifact_ids: tuple[str, ...] = ()
    output_artifact_ids: tuple[str, ...] = ()
    counts: dict[str, int] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="python")
        payload["timestamp"] = self.timestamp.isoformat()
        if self.decision_time is not None:
            payload["decision_time"] = self.decision_time.isoformat()
        return payload
