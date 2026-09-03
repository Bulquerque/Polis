from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from quant_pipeline.phase_08_portfolio_control.foundation.models import NonEmptyStr, StrictModel, TimeAwareModel
from .enums import StatefulEventKind, StatefulPriority


class StatefulEventEnvelope(TimeAwareModel):
    event_key: NonEmptyStr
    event_time: datetime
    available_at: datetime
    apply_at: datetime
    priority: StatefulPriority
    kind: StatefulEventKind
    payload: Any
    source_sequence: int = Field(default=0, ge=0)


class OrderedEventQueue(StrictModel):
    events: tuple[StatefulEventEnvelope, ...]
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
