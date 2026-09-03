from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash

from .normalization import artifact_identity, artifact_records, parse_datetime
from .ports import VisibleRecordBatch

_VISIBILITY_FIELDS = {
    "clean_underlying_panel": "available_at",
    "clean_underlying_trade_panel": "available_at",
    "clean_corporate_actions_panel": "available_at",
    "clean_benchmark_panel": "available_at",
    "clean_option_contract_panel": "first_seen_date",
    "clean_option_quotes_panel": "available_at",
    "clean_liquidity_reference_panel": "available_at",
    "clean_cost_reference_panel": "available_at",
}


class InMemoryPitMarketBoundary:
    """Frozen, offline adapter used by tests and local qualification.

    Production composition may replace this adapter with the S33 boundary port,
    while preserving this contract and temporal behavior.
    """

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
    ) -> VisibleRecordBatch:
        if decision_time.tzinfo is None or decision_time.utcoffset() is None:
            raise ValueError("decision_time must be timezone-aware")
        decision = decision_time.astimezone(UTC)
        rows = self._rows.get(view_name, ())
        visibility_field = _VISIBILITY_FIELDS.get(view_name)
        visible: list[Mapping[str, object]] = []
        rejected_future = 0
        rejected_missing = 0
        rejected_filter = 0
        for row in rows:
            if visibility_field is None or row.get(visibility_field) in (None, ""):
                rejected_missing += 1
                continue
            available = parse_datetime(row[visibility_field], field=visibility_field)
            if available > decision:
                rejected_future += 1
                continue
            if not self._matches(row, filters or {}):
                rejected_filter += 1
                continue
            visible.append(dict(row))
        visible.sort(key=lambda row: self._sort_key(view_name, row))
        input_hash = content_hash(tuple(visible))
        return VisibleRecordBatch(
            view_name=view_name,
            snapshot_id=self._snapshot_id,
            rows=tuple(visible),
            records_scanned=len(rows),
            records_rejected_future=rejected_future,
            records_rejected_missing_time=rejected_missing,
            records_rejected_filter=rejected_filter,
            input_hashes=(input_hash,),
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

    @staticmethod
    def _sort_key(view_name: str, row: Mapping[str, object]) -> tuple[str, ...]:
        if view_name == "clean_option_contract_panel":
            return (
                str(row.get("expiration_date") or ""),
                str(row.get("strike") or ""),
                str(row.get("option_type") or ""),
                str(row.get("contract_key") or ""),
            )
        return (
            str(row.get("date") or row.get("available_at") or ""),
            str(row.get("underlying") or row.get("benchmark_id") or ""),
            str(row.get("contract_key") or ""),
        )
