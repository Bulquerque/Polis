"""Adapter from P3.S37 macro bundles to the canonical S40 registry."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.macro.factory import create_macro_runtime_bundle
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.macro.models import (
    AssetMacroContextRegistrySnapshot,
    HandlerBundleManifest,
    MacroSeriesReleaseCatalog,
    MacroToolCallContext,
    OperationModeQualificationPanel,
)

from .canonical_support import adapt_result, canonical_context, operation
from .models import QualificationStatus
from .registry import ExecutableOperation


def _status_by_operation(panel: OperationModeQualificationPanel | None) -> Mapping[str, QualificationStatus]:
    if panel is None:
        return {}
    grouped: dict[str, list[str]] = {}
    for record in panel.records:
        grouped.setdefault(record.operation_id, []).append(str(record.status.value))
    result: dict[str, QualificationStatus] = {}
    for operation_id, statuses in grouped.items():
        if "FAILED" in statuses:
            result[operation_id] = QualificationStatus.FAILED
        elif set(statuses) == {"BLOCKED_UPSTREAM"}:
            result[operation_id] = QualificationStatus.BLOCKED_UPSTREAM
        elif "DEGRADED" in statuses or "BLOCKED_UPSTREAM" in statuses:
            result[operation_id] = QualificationStatus.DEGRADED
        else:
            result[operation_id] = QualificationStatus.QUALIFIED_LOCAL
    return result


def _calls(
    request: BaseModel,
    operation_id: str,
    *,
    catalog: MacroSeriesReleaseCatalog,
) -> tuple[dict[str, Any], ...]:
    data = request.model_dump(mode="python")
    mode = data["research_mode"]
    if operation_id == "search_series":
        return ({
            "query": data["query"],
            "regions": tuple(data["regions"]),
            "countries": (),
            "families": tuple(data["categories"]),
            "frequencies": (),
            "source_ids": (),
            "research_mode": mode,
            "max_results": data["max_results"],
        },)
    if operation_id == "get_observations":
        transformation = data["transformations"][0] if data["transformations"] else "LEVEL"
        return tuple({
            "series_id": series_id,
            "start_date": data["start_time"].date(),
            "end_date": data["end_time"].date(),
            "transformation": transformation,
            "vintage_policy": data["vintage_policy"],
            "research_mode": mode,
            "max_records": 10000,
        } for series_id in data["series_ids"])
    if operation_id == "get_release_snapshot":
        calls: list[dict[str, Any]] = []
        for series_id in data["series_ids"]:
            calls.append({"series_id": series_id, "release_id": None, "vintage_date": None, "vintage_policy": "KNOWN_AT_DECISION_TIME", "research_mode": mode, "max_records": 1000})
        for release_id in data["release_ids"]:
            series_id = next(
                (
                    str(item.series_id)
                    for item in catalog.records
                    if str(item.release_id) == str(release_id)
                ),
                None,
            )
            if series_id is None:
                raise ValueError(f"release_id is not bound to a known series: {release_id}")
            calls.append({"series_id": series_id, "release_id": release_id, "vintage_date": None, "vintage_policy": "KNOWN_AT_DECISION_TIME", "research_mode": mode, "max_records": 1000})
        return tuple(calls)
    if operation_id == "compare_series":
        kind = {"NONE": "RAW_ALIGNED", "INDEX_100": "INDEX_BASE_100", "ZSCORE_HISTORY_ONLY": "RAW_ALIGNED"}[data["normalization"]]
        return ({
            "series_ids": tuple(data["series_ids"]),
            "start_date": data["start_time"].date(),
            "end_date": data["end_time"].date(),
            "transformations": {},
            "vintage_policy": "KNOWN_AT_DECISION_TIME",
            "comparison_kind": kind,
            "alignment": "INNER",
            "research_mode": mode,
            "max_records_per_series": 10000,
        },)
    if operation_id == "get_asset_context":
        return tuple({
            "asset_id": instrument_id,
            "regions": (),
            "families": tuple(data["factor_categories"]),
            "research_mode": mode,
            "max_factors": min(100, max(1, int(data["lookback_observations"]))),
        } for instrument_id in data["instrument_ids"])
    raise KeyError(operation_id)


def build_macro_operations(*, inputs: Mapping[str, Any], services: Mapping[str, Any]) -> tuple[ExecutableOperation, ...]:
    if "macro_tool_handler_bundle" not in inputs:
        return ()
    boundary = services.get("pit_macro_query_port")
    if boundary is None:
        return ()
    manifest = HandlerBundleManifest.model_validate(inputs["macro_tool_handler_bundle"], strict=False)
    catalog = MacroSeriesReleaseCatalog.model_validate(inputs["macro_series_release_catalog"], strict=False)
    contexts = AssetMacroContextRegistrySnapshot.model_validate(inputs["macro_asset_context_config_snapshot"], strict=False)
    panel = None
    if inputs.get("macro_operation_mode_qualification") is not None:
        panel = OperationModeQualificationPanel.model_validate(inputs["macro_operation_mode_qualification"], strict=False)
    runtime_bundle = create_macro_runtime_bundle(boundary, catalog, contexts)
    statuses = _status_by_operation(panel)
    operations: list[ExecutableOperation] = []
    for binding in manifest.handlers:
        operation_id = binding.operation_id

        async def handler(request: BaseModel, context: MacroToolCallContext, *, _operation_id: str = operation_id) -> BaseModel:
            envelopes = [
                await runtime_bundle.execute("macro.observation.v1", _operation_id, arguments, context)
                for arguments in _calls(request, _operation_id, catalog=catalog)
            ]
            return adapt_result(tool_id="macro.observation.v1", operation_id=_operation_id, request=request, envelopes=envelopes)

        operations.append(operation(
            inputs=inputs,
            tool_id="macro.observation.v1",
            operation_id=operation_id,
            bundle_id=manifest.content_hash,
            qualification_status=statuses.get(operation_id, QualificationStatus.DEGRADED),
            handler=handler,
            context_factory=lambda invocation: canonical_context(invocation, MacroToolCallContext),
            fallback_binding=binding,
        ))
    return tuple(operations)
