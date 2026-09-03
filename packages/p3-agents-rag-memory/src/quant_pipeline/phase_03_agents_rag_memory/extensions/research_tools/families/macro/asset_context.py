from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from pydantic import JsonValue

from ._compat import validate_json
from .catalog_contracts import (
    AssetMacroContextDefinition,
    AssetMacroContextRegistrySnapshot,
)
from .ports import VisibleMacroRecordBatch
from .request_contracts import GetAssetContextRequest, MacroToolCallContext
from .result_contracts import AssetMacroFactor, MacroToolResultEnvelope
from .support import build_envelope
from .types import VintagePolicy


class MacroAssetContextHandler:
    def __init__(self, registry: AssetMacroContextRegistrySnapshot) -> None:
        self._registry = registry

    async def execute(
        self,
        arguments: Mapping[str, JsonValue],
        context: MacroToolCallContext,
    ) -> MacroToolResultEnvelope:
        request = validate_json(GetAssetContextRequest, arguments)
        selected, rejected_future = self._selected_contexts(request, context)
        factors = tuple(
            AssetMacroFactor(**item.model_dump()).model_dump(mode="json")
            for item in selected
        )
        batch = self._batch(selected, rejected_future, context)
        return build_envelope(
            operation_id="get_asset_context",
            context=context,
            requested_mode=request.research_mode.value,
            executed_mode=request.research_mode.value,
            records=factors,
            batches=(batch,),
            source_rows=tuple(item.model_dump(mode="json") for item in selected),
            vintage_policy=VintagePolicy.KNOWN_AT_DECISION_TIME,
            series_requested=1,
            series_returned=1 if factors else 0,
            missing_series=() if factors else (request.asset_id,),
        )

    def _selected_contexts(
        self,
        request: GetAssetContextRequest,
        context: MacroToolCallContext,
    ) -> tuple[tuple[AssetMacroContextDefinition, ...], int]:
        selected = []
        rejected_future = 0
        for item in self._registry.records:
            if item.asset_id != request.asset_id:
                continue
            if item.available_at > context.decision_time:
                rejected_future += 1
                continue
            if self._matches(item, request, context.decision_time.date()):
                selected.append(item)
        selected.sort(key=lambda item: (item.family, item.factor_id))
        return tuple(selected[: request.max_factors]), rejected_future

    @staticmethod
    def _matches(
        item: AssetMacroContextDefinition,
        request: GetAssetContextRequest,
        current_date: date,
    ) -> bool:
        checks = (
            item.valid_from is None or current_date >= item.valid_from,
            item.valid_to is None or current_date <= item.valid_to,
            not request.regions or (item.region or "") in request.regions,
            not request.families or item.family in request.families,
        )
        return all(checks)

    def _batch(
        self,
        selected: tuple[AssetMacroContextDefinition, ...],
        rejected_future: int,
        context: MacroToolCallContext,
    ) -> VisibleMacroRecordBatch:
        return VisibleMacroRecordBatch(
            view_name="asset_macro_context_registry",
            snapshot_id=context.snapshot_id,
            rows=tuple(item.model_dump(mode="python") for item in selected),
            records_scanned=len(self._registry.records),
            records_rejected_future=rejected_future,
            records_rejected_missing_time=0,
            records_rejected_filter=max(
                0,
                len(self._registry.records) - len(selected) - rejected_future,
            ),
            input_hashes=(self._registry.content_hash,),
        )
