from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class VisibleMacroRecordBatch:
    view_name: str
    snapshot_id: str
    rows: tuple[Mapping[str, object], ...]
    records_scanned: int
    records_rejected_future: int
    records_rejected_missing_time: int
    records_rejected_filter: int
    input_hashes: tuple[str, ...]


class PitMacroQueryPort(Protocol):
    def query(
        self,
        view_name: str,
        *,
        decision_time: datetime,
        filters: Mapping[str, object] | None = None,
    ) -> VisibleMacroRecordBatch:
        """Return immutable records visible at decision_time."""

    def available_fields(self, view_name: str) -> frozenset[str]:
        """Return fields observed in the frozen view snapshot."""

    def record_count(self, view_name: str) -> int:
        """Return raw frozen record count."""
