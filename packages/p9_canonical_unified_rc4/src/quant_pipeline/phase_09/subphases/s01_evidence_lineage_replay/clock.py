from __future__ import annotations

from datetime import datetime
from typing import Protocol

from quant_pipeline.phase_09.contracts.base import ensure_utc


class ClockPort(Protocol):
    def now(self) -> datetime:
        """Returns an aware UTC datetime."""


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self._value = ensure_utc(value)

    def now(self) -> datetime:
        return self._value
