from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from pydantic import JsonValue

from ._compat import validate_json
from .catalog_contracts import MacroSeriesReleaseCatalog
from .normalization import observation_date, series_id
from .ports import PitMacroQueryPort, VisibleMacroRecordBatch
from .request_contracts import (
    GetObservationsRequest,
    GetReleaseSnapshotRequest,
    MacroToolCallContext,
)
from .result_contracts import (
    MacroObservation,
    MacroSeriesDefinition,
    MacroToolResultEnvelope,
)
from .support import build_envelope
from .transformations import apply_transformation
from .types import MacroMode, OutcomeStatus, Transformation, VintagePolicy
from .vintage_support import (
    date_in_range,
    history_warnings,
    release_filter,
    request_issue,
    select_vintage,
    source_rows_for_transformation,
    to_observation,
)

_MACRO_VIEWS = ("clean_macro_br_panel", "clean_macro_us_panel")


class MacroVintageObservationHandler:
    def __init__(
        self,
        boundary: PitMacroQueryPort,
        catalog: MacroSeriesReleaseCatalog,
    ) -> None:
        self._boundary = boundary
        self._definitions = {item.series_id: item for item in catalog.records}

    async def get_observations(
        self,
        arguments: Mapping[str, JsonValue],
        context: MacroToolCallContext,
    ) -> MacroToolResultEnvelope:
        request = validate_json(GetObservationsRequest, arguments)
        definition = self._definitions.get(request.series_id)
        issue = request_issue(request, definition)
        if issue is not None:
            return self._blocked_or_empty(
                "get_observations",
                request.research_mode,
                request.vintage_policy,
                context,
                request.series_id,
                issue,
            )
        assert definition is not None
        batches, rows = self._query_series(request.series_id, context)
        selected = self._selected_rows(rows, request)
        try:
            transformed = apply_transformation(
                tuple(to_observation(row, definition) for row in selected),
                request.transformation,
            )
        except ValueError as exc:
            return self._transformation_failure(request, context, batches, exc)
        return self._observation_result(
            request,
            context,
            definition,
            batches,
            selected,
            transformed,
        )

    async def get_release_snapshot(
        self,
        arguments: Mapping[str, JsonValue],
        context: MacroToolCallContext,
    ) -> MacroToolResultEnvelope:
        request = validate_json(GetReleaseSnapshotRequest, arguments)
        definition = self._definitions.get(request.series_id)
        if definition is None or not definition.vintage_support:
            return self._blocked_or_empty(
                "get_release_snapshot",
                request.research_mode,
                request.vintage_policy,
                context,
                request.series_id,
                "P3_RT_PIT_VINTAGE_UNAVAILABLE",
            )
        batches, rows = self._query_series(request.series_id, context)
        filtered = release_filter(rows, request)
        selected = select_vintage(filtered, request.vintage_policy)
        source_rows = selected[-request.max_records :]
        records = tuple(
            to_observation(row, definition).model_dump(mode="json")
            for row in source_rows
        )
        return build_envelope(
            operation_id="get_release_snapshot",
            context=context,
            requested_mode=request.research_mode.value,
            executed_mode=request.research_mode.value,
            records=records,
            batches=batches,
            source_rows=source_rows,
            vintage_policy=request.vintage_policy,
            series_requested=1,
            series_returned=1 if records else 0,
            missing_series=() if records else (request.series_id,),
            truncated=len(selected) > request.max_records,
        )

    def _query_series(
        self,
        sid: str,
        context: MacroToolCallContext,
    ) -> tuple[
        tuple[VisibleMacroRecordBatch, ...],
        tuple[Mapping[str, object], ...],
    ]:
        batches = tuple(
            self._boundary.query(view, decision_time=context.decision_time)
            for view in _MACRO_VIEWS
        )
        rows = tuple(
            row
            for batch in batches
            for row in batch.rows
            if series_id(row) == sid
        )
        return batches, rows

    def _selected_rows(
        self,
        rows: tuple[Mapping[str, object], ...],
        request: GetObservationsRequest,
    ) -> tuple[Mapping[str, object], ...]:
        selected = select_vintage(rows, request.vintage_policy)
        return tuple(
            row
            for row in selected
            if date_in_range(
                observation_date(row),
                request.start_date,
                request.end_date,
            )
        )

    def _observation_result(
        self,
        request: GetObservationsRequest,
        context: MacroToolCallContext,
        definition: MacroSeriesDefinition,
        batches: tuple[VisibleMacroRecordBatch, ...],
        selected: tuple[Mapping[str, object], ...],
        transformed: tuple[MacroObservation, ...],
    ) -> MacroToolResultEnvelope:
        returned = transformed[-request.max_records :]
        records = tuple(item.model_dump(mode="json") for item in returned)
        source_rows = source_rows_for_transformation(
            selected,
            returned,
            definition,
            request.transformation,
        )
        warnings = history_warnings(selected, records, request.transformation)
        return build_envelope(
            operation_id="get_observations",
            context=context,
            requested_mode=request.research_mode.value,
            executed_mode=request.research_mode.value,
            records=records,
            batches=batches,
            source_rows=source_rows,
            vintage_policy=request.vintage_policy,
            series_requested=1,
            series_returned=1 if records else 0,
            missing_series=() if records else (request.series_id,),
            warnings=warnings,
            truncated=len(transformed) > request.max_records,
        )

    def _transformation_failure(
        self,
        request: GetObservationsRequest,
        context: MacroToolCallContext,
        batches: tuple[VisibleMacroRecordBatch, ...],
        error: ValueError,
    ) -> MacroToolResultEnvelope:
        return self._blocked_or_empty(
            "get_observations",
            request.research_mode,
            request.vintage_policy,
            context,
            request.series_id,
            f"P3_RT_DATA_TRANSFORMATION_FAILED:{error}",
            batches=batches,
        )

    @staticmethod
    def _blocked_or_empty(
        operation: str,
        mode: MacroMode,
        policy: VintagePolicy,
        context: MacroToolCallContext,
        sid: str,
        reason: str,
        *,
        batches: tuple[VisibleMacroRecordBatch, ...] = (),
    ) -> MacroToolResultEnvelope:
        return build_envelope(
            operation_id=operation,
            context=context,
            requested_mode=mode.value,
            executed_mode=mode.value,
            records=(),
            batches=batches,
            source_rows=(),
            vintage_policy=policy,
            series_requested=1,
            series_returned=0,
            missing_series=(sid,),
            warnings=(reason,),
            outcome_status=OutcomeStatus.BLOCKED_UPSTREAM,
        )
