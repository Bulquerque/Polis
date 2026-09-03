from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from pydantic import JsonValue

from ._compat import validate_json
from .catalog_contracts import MacroSeriesReleaseCatalog
from .normalization import available_at, observation_date, revision_id, series_id
from .observations import MacroObservationHandlers
from .ports import PitMacroQueryPort, VisibleMacroRecordBatch
from .request_contracts import CompareSeriesRequest, MacroToolCallContext
from .result_contracts import MacroComparisonRow, MacroToolResultEnvelope
from .support import build_envelope
from .types import AlignmentPolicy, ComparisonKind, OutcomeStatus, VintagePolicy

_MACRO_VIEWS = ("clean_macro_br_panel", "clean_macro_us_panel")


class MacroSeriesComparisonHandler:
    def __init__(
        self,
        boundary: PitMacroQueryPort,
        catalog: MacroSeriesReleaseCatalog,
    ) -> None:
        self._boundary = boundary
        self._observations = MacroObservationHandlers(boundary, catalog)

    async def execute(
        self,
        arguments: Mapping[str, JsonValue],
        context: MacroToolCallContext,
    ) -> MacroToolResultEnvelope:
        request = validate_json(CompareSeriesRequest, arguments)
        batches = self._macro_batches(context)
        series_values: dict[str, dict[date, float]] = {}
        source_rows: list[Mapping[str, object]] = []
        missing = []
        for sid in request.series_ids:
            values = await self._series_values(sid, request, context)
            if values:
                series_values[sid] = values
            else:
                missing.append(sid)
            source_rows.extend(self._source_rows(sid, request, batches))
        records = self._comparison_records(request, series_values)
        return build_envelope(
            operation_id="compare_series",
            context=context,
            requested_mode=request.research_mode.value,
            executed_mode=request.research_mode.value,
            records=records,
            batches=batches,
            source_rows=tuple(source_rows),
            vintage_policy=request.vintage_policy,
            series_requested=len(request.series_ids),
            series_returned=len(series_values),
            missing_series=tuple(missing),
            warnings=("P3_RT_DATA_SERIES_PARTIAL",) if missing else (),
            outcome_status=self._status(records, missing),
        )

    async def _series_values(
        self,
        sid: str,
        request: CompareSeriesRequest,
        context: MacroToolCallContext,
    ) -> dict[date, float]:
        envelope = await self._observations.get_observations(
            {
                "series_id": sid,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "transformation": request.transformations.get(sid, "LEVEL"),
                "vintage_policy": request.vintage_policy,
                "research_mode": request.research_mode,
                "max_records": request.max_records_per_series,
            },
            context,
        )
        if envelope.outcome_status is OutcomeStatus.BLOCKED_UPSTREAM:
            return {}
        return {
            date.fromisoformat(str(row["observation_date"])[:10]): float(row["value"])
            for row in envelope.records
        }

    def _macro_batches(
        self,
        context: MacroToolCallContext,
    ) -> tuple[VisibleMacroRecordBatch, ...]:
        return tuple(
            self._boundary.query(view, decision_time=context.decision_time)
            for view in _MACRO_VIEWS
        )

    def _source_rows(
        self,
        sid: str,
        request: CompareSeriesRequest,
        batches: tuple[VisibleMacroRecordBatch, ...],
    ) -> tuple[Mapping[str, object], ...]:
        rows = tuple(
            row
            for batch in batches
            for row in batch.rows
            if series_id(row) == sid
            and self._date_in_range(
                observation_date(row),
                request.start_date,
                request.end_date,
            )
        )
        return self._select_vintage(rows, request.vintage_policy)

    @staticmethod
    def _select_vintage(
        rows: tuple[Mapping[str, object], ...],
        policy: VintagePolicy,
    ) -> tuple[Mapping[str, object], ...]:
        grouped: dict[date, list[Mapping[str, object]]] = {}
        for row in rows:
            grouped.setdefault(observation_date(row), []).append(row)
        selected = []
        for candidates in grouped.values():
            candidates.sort(key=lambda row: (available_at(row), revision_id(row) or ""))
            selected.append(
                candidates[0]
                if policy is VintagePolicy.ORIGINAL_RELEASE
                else candidates[-1]
            )
        return tuple(sorted(selected, key=observation_date))

    def _comparison_records(
        self,
        request: CompareSeriesRequest,
        series_values: Mapping[str, Mapping[date, float]],
    ) -> tuple[dict[str, JsonValue], ...]:
        dates = self._aligned_dates(series_values, request.alignment)
        baselines = self._base_values(series_values)
        return tuple(
            self._comparison_row(
                day,
                request.series_ids,
                series_values,
                request.comparison_kind,
                baselines,
            ).model_dump(mode="json")
            for day in dates
        )

    @staticmethod
    def _status(
        records: tuple[dict[str, JsonValue], ...],
        missing: list[str],
    ) -> OutcomeStatus:
        if not records:
            return OutcomeStatus.EMPTY_VALID
        if missing:
            return OutcomeStatus.DEGRADED
        return OutcomeStatus.PASS

    @staticmethod
    def _aligned_dates(
        series: Mapping[str, Mapping[date, float]],
        alignment: AlignmentPolicy,
    ) -> tuple[date, ...]:
        date_sets = [set(values) for values in series.values()]
        if not date_sets:
            return ()
        dates = (
            set.intersection(*date_sets)
            if alignment is AlignmentPolicy.INNER
            else set.union(*date_sets)
        )
        return tuple(sorted(dates))

    @staticmethod
    def _base_values(
        series: Mapping[str, Mapping[date, float]],
    ) -> dict[str, float | None]:
        return {
            sid: values[min(values)] if values else None
            for sid, values in series.items()
        }

    @staticmethod
    def _comparison_row(
        day: date,
        series_ids: tuple[str, ...],
        values: Mapping[str, Mapping[date, float]],
        kind: ComparisonKind,
        baselines: Mapping[str, float | None],
    ) -> MacroComparisonRow:
        raw = {sid: values.get(sid, {}).get(day) for sid in series_ids}
        derived = MacroSeriesComparisonHandler._derived_values(
            raw,
            series_ids,
            kind,
            baselines,
        )
        return MacroComparisonRow(
            observation_date=day,
            values=raw,
            derived_values=derived,
        )

    @staticmethod
    def _derived_values(
        raw: Mapping[str, float | None],
        series_ids: tuple[str, ...],
        kind: ComparisonKind,
        baselines: Mapping[str, float | None],
    ) -> dict[str, float | None]:
        if kind is ComparisonKind.INDEX_BASE_100:
            return {
                f"{sid}_base_100": MacroSeriesComparisonHandler._base_100(
                    raw[sid], baselines.get(sid)
                )
                for sid in series_ids
            }
        first = raw.get(series_ids[0])
        if kind in {
            ComparisonKind.DIFFERENCE_FROM_FIRST,
            ComparisonKind.SPREAD_TO_FIRST,
        }:
            return {
                f"{sid}_minus_{series_ids[0]}": (
                    None if first is None or raw[sid] is None else raw[sid] - first
                )
                for sid in series_ids[1:]
            }
        if kind is ComparisonKind.RATIO_TO_FIRST:
            return {
                f"{sid}_to_{series_ids[0]}": MacroSeriesComparisonHandler._ratio(
                    raw[sid], first
                )
                for sid in series_ids[1:]
            }
        return {}

    @staticmethod
    def _base_100(value: float | None, baseline: float | None) -> float | None:
        if value is None or baseline in (None, 0):
            return None
        return value / float(baseline) * 100.0

    @staticmethod
    def _ratio(value: float | None, denominator: float | None) -> float | None:
        if value is None or denominator in (None, 0):
            return None
        return value / float(denominator)

    @staticmethod
    def _date_in_range(
        value: date,
        start: date | None,
        end: date | None,
    ) -> bool:
        return (start is None or value >= start) and (end is None or value <= end)
