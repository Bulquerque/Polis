from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue

from ._compat import validate_json
from .catalog_contracts import MacroSeriesReleaseCatalog
from .normalization import series_id
from .ports import PitMacroQueryPort, VisibleMacroRecordBatch
from .request_contracts import MacroToolCallContext, SearchSeriesRequest
from .result_contracts import MacroSeriesDefinition, MacroToolResultEnvelope
from .support import build_envelope
from .types import VintagePolicy

_MACRO_VIEWS = ("clean_macro_br_panel", "clean_macro_us_panel")


class MacroSeriesSearchHandler:
    def __init__(
        self,
        boundary: PitMacroQueryPort,
        catalog: MacroSeriesReleaseCatalog,
    ) -> None:
        self._boundary = boundary
        self._catalog = catalog

    async def execute(
        self,
        arguments: Mapping[str, JsonValue],
        context: MacroToolCallContext,
    ) -> MacroToolResultEnvelope:
        request = validate_json(SearchSeriesRequest, arguments)
        batches, visible_series, first_rows = self._visible_catalog(context)
        query = request.query.casefold().strip()
        matches = [
            (self._search_score(item, query), item)
            for item in self._catalog.records
            if item.series_id in visible_series
            and self._matches_search(item, request, query)
        ]
        matches.sort(key=lambda pair: (-pair[0], pair[1].series_id))
        selected = tuple(item for _, item in matches[: request.max_results])
        records = tuple(item.model_dump(mode="json") for item in selected)
        source_rows = tuple(
            first_rows[item.series_id]
            for item in selected
            if item.series_id in first_rows
        )
        return build_envelope(
            operation_id="search_series",
            context=context,
            requested_mode=request.research_mode.value,
            executed_mode=request.research_mode.value,
            records=records,
            batches=batches,
            source_rows=source_rows,
            vintage_policy=VintagePolicy.KNOWN_AT_DECISION_TIME,
            series_requested=1,
            series_returned=1 if records else 0,
            truncated=len(matches) > request.max_results,
        )

    def _visible_catalog(
        self,
        context: MacroToolCallContext,
    ) -> tuple[
        tuple[VisibleMacroRecordBatch, ...],
        set[str],
        dict[str, Mapping[str, object]],
    ]:
        batches = tuple(
            self._boundary.query(view, decision_time=context.decision_time)
            for view in _MACRO_VIEWS
        )
        visible_series: set[str] = set()
        first_rows: dict[str, Mapping[str, object]] = {}
        for batch in batches:
            for row in batch.rows:
                sid = series_id(row)
                if sid is None:
                    continue
                visible_series.add(sid)
                first_rows.setdefault(sid, row)
        return batches, visible_series, first_rows

    @staticmethod
    def _matches_search(
        item: MacroSeriesDefinition,
        request: SearchSeriesRequest,
        query: str,
    ) -> bool:
        text = " ".join(
            (item.series_id, item.title, *item.aliases, item.description or "")
        ).casefold()
        checks = (
            not query or query in text,
            not request.regions or (item.region or "") in request.regions,
            not request.countries or (item.country or "") in request.countries,
            not request.families or (item.family or "") in request.families,
            not request.frequencies or item.frequency.value in request.frequencies,
            not request.source_ids or item.source_id in request.source_ids,
        )
        return all(checks)

    @staticmethod
    def _search_score(item: MacroSeriesDefinition, query: str) -> int:
        if not query:
            return 0
        if item.series_id.casefold() == query:
            return 100
        if item.title.casefold() == query:
            return 80
        if query in {alias.casefold() for alias in item.aliases}:
            return 70
        return 10
