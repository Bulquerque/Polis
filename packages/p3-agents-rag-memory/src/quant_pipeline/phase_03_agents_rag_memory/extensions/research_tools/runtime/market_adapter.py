"""Adapter from P3.S36 market bundles to the canonical S40 registry."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.factory import create_market_derivatives_runtime_bundle
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.models import (
    HandlerBundleManifest,
    MarketToolCallContext,
    OperationModeQualificationPanel,
)

from .canonical_support import adapt_result, canonical_context, operation
from .models import QualificationStatus
from .registry import ExecutableOperation


def qualification_by_operation(panel: OperationModeQualificationPanel | None) -> Mapping[tuple[str, str], QualificationStatus]:
    if panel is None:
        return {}
    grouped: dict[tuple[str, str], list[str]] = {}
    for record in panel.records:
        grouped.setdefault((record.tool_id, record.operation_id), []).append(str(record.status.value))
    result: dict[tuple[str, str], QualificationStatus] = {}
    for key, statuses in grouped.items():
        if "FAILED" in statuses:
            result[key] = QualificationStatus.FAILED
        elif set(statuses) == {"BLOCKED_UPSTREAM"}:
            result[key] = QualificationStatus.BLOCKED_UPSTREAM
        elif "DEGRADED" in statuses or "BLOCKED_UPSTREAM" in statuses:
            result[key] = QualificationStatus.DEGRADED
        else:
            result[key] = QualificationStatus.QUALIFIED_LOCAL
    return result


def _market_calls(request: BaseModel, operation_id: str) -> tuple[dict[str, Any], ...]:
    data = request.model_dump(mode="python")
    mode = data["research_mode"]
    ids = tuple(data.get("instrument_ids", ()))
    if operation_id == "get_snapshot":
        return tuple({"instrument_id": item, "research_mode": mode, "max_staleness_seconds": None} for item in ids)
    if operation_id == "get_history":
        return tuple({
            "instrument_id": item,
            "start_date": data["start_time"].date(),
            "end_date": data["end_time"].date(),
            "research_mode": mode,
            "adjustment_policy": "RAW",
            "max_records": 5000,
        } for item in ids)
    if operation_id == "get_liquidity":
        return tuple({"instrument_id": item, "lookback_days": data["lookback_observations"], "research_mode": mode} for item in ids)
    if operation_id == "get_corporate_actions":
        return tuple({
            "instrument_id": item,
            "start_date": data["start_time"].date() if data["start_time"] else None,
            "end_date": data["end_time"].date() if data["end_time"] else None,
            "research_mode": mode,
        } for item in ids)
    if operation_id == "compare_instruments":
        normalization = {"BASE_100": "BASE_100", "NONE": "NONE", "ZSCORE_HISTORY_ONLY": "NONE"}[data["normalization"]]
        return ({
            "instrument_ids": ids,
            "start_date": data["start_time"].date(),
            "end_date": data["end_time"].date(),
            "normalization": normalization,
            "research_mode": mode,
            "max_records_per_instrument": 5000,
        },)
    raise KeyError(operation_id)


def build_market_operations(*, inputs: Mapping[str, Any], services: Mapping[str, Any]) -> tuple[ExecutableOperation, ...]:
    if "market_tool_handler_bundle" not in inputs:
        return ()
    boundary = services.get("pit_market_query_port")
    if boundary is None:
        return ()
    manifest = HandlerBundleManifest.model_validate(inputs["market_tool_handler_bundle"], strict=False)
    panel = None
    if inputs.get("market_derivatives_operation_mode_qualification") is not None:
        panel = OperationModeQualificationPanel.model_validate(inputs["market_derivatives_operation_mode_qualification"], strict=False)
    runtime_bundle = create_market_derivatives_runtime_bundle(boundary)
    statuses = qualification_by_operation(panel)
    operations: list[ExecutableOperation] = []
    for binding in manifest.handlers:
        operation_id = binding.operation_id

        async def handler(request: BaseModel, context: MarketToolCallContext, *, _operation_id: str = operation_id) -> BaseModel:
            envelopes = [
                await runtime_bundle.execute("market.observation.v1", _operation_id, arguments, context)
                for arguments in _market_calls(request, _operation_id)
            ]
            return adapt_result(tool_id="market.observation.v1", operation_id=_operation_id, request=request, envelopes=envelopes)

        operations.append(operation(
            inputs=inputs,
            tool_id="market.observation.v1",
            operation_id=operation_id,
            bundle_id=manifest.content_hash,
            qualification_status=statuses.get(("market.observation.v1", operation_id), QualificationStatus.DEGRADED),
            handler=handler,
            context_factory=lambda invocation: canonical_context(invocation, MarketToolCallContext),
            fallback_binding=binding,
        ))
    return tuple(operations)
