"""S8-specific records received through the S7 handoff."""
from __future__ import annotations

from datetime import datetime

from pydantic import field_validator

from .base import FrozenModel, _aware


class ScoreDecompositionRecord(FrozenModel):
    cycle_id: str
    decision_time: datetime
    candidate_id: str
    head: str
    contribution: float
    lineage_id: str

    _decision_aware = field_validator("decision_time")(_aware)
