from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType

from ._compat import content_hash
from .normalization import artifact_identity, artifact_records, available_at, row_sort_key
from .ports import VisibleMacroRecordBatch


class InMemoryPitMacroBoundary:
    """Frozen offline boundary for local qualification and deterministic replay."""

    def __init__(self, *, snapshot_id: str, artifacts: Mapping[str, object]) -> None:
        self._snapshot_id = snapshot_id
        self._rows = MappingProxyType(
            {name: artifact_records(value) for name, value in artifacts.items()}
        )
        self._hashes = MappingProxyType(
            {name: artifact_identity(name, value)[2] for name, value in artifacts.items()}
        )

    def available_fields(self, view_name: str) -> frozenset[str]:
        return frozenset(key for row in self._rows.get(view_name, ()) for key in row)

    def record_count(self, view_name: str) -> int:
        return len(self._rows.get(view_name, ()))

    def query(
        self,
        view_name: str,
        *,
        decision_time: datetime,
        filters: Mapping[str, object] | None = None,
    ) -> VisibleMacroRecordBatch:
        if decision_time.tzinfo is None or decision_time.utcoffset() is None:
            raise ValueError("decision_time must be timezone-aware")
        decision = decision_time.astimezone(UTC)
        rows = self._rows.get(view_name, ())
        visible: list[Mapping[str, object]] = []
        rejected_future = 0
        rejected_missing = 0
        rejected_filter = 0
        for row in rows:
            try:
                visible_at = available_at(row)
            except ValueError:
                rejected_missing += 1
                continue
            if visible_at > decision:
                rejected_future += 1
                continue
            if not self._matches(row, filters or {}):
                rejected_filter += 1
                continue
            visible.append(dict(row))
        visible.sort(key=row_sort_key)
        return VisibleMacroRecordBatch(
            view_name=view_name,
            snapshot_id=self._snapshot_id,
            rows=tuple(visible),
            records_scanned=len(rows),
            records_rejected_future=rejected_future,
            records_rejected_missing_time=rejected_missing,
            records_rejected_filter=rejected_filter,
            input_hashes=(content_hash(tuple(visible)),),
        )

    @staticmethod
    def _matches(row: Mapping[str, object], filters: Mapping[str, object]) -> bool:
        for field, expected in filters.items():
            if expected is None:
                continue
            actual = row.get(field)
            if isinstance(expected, (set, frozenset, tuple, list)):
                if actual not in expected:
                    return False
            elif str(actual) != str(expected):
                return False
        return True
