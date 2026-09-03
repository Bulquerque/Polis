"""Immutable run context shared across all subphases."""

from datetime import datetime

from .artifacts import FrozenModel
from .configuration import Phase6RunConfiguration


class PhaseContext(FrozenModel):
    run_id: str
    cycle_id: str
    decision_time: datetime
    created_at: datetime
    available_at: datetime
    seed: int

    @classmethod
    def from_configuration(cls, configuration: Phase6RunConfiguration) -> "PhaseContext":
        return cls(
            run_id=configuration.run_id,
            cycle_id=configuration.cycle_id,
            decision_time=configuration.decision_time,
            created_at=configuration.created_at,
            available_at=configuration.available_at,
            seed=configuration.seed,
        )
