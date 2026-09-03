"""Adapter from P3.S36 options bundles to the canonical S40 registry."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.factory import create_market_derivatives_runtime_bundle
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.models import HandlerBundleManifest, MarketToolCallContext, OperationModeQualificationPanel

from .canonical_support import adapt_result, canonical_context, operation
from .market_adapter import qualification_by_operation
from .models import QualificationStatus
from .registry import ExecutableOperation


def _option_calls(request: BaseModel, operation_id: str) -> tuple[dict[str, Any], ...]:
    data = request.model_dump(mode="python")
    mode = data["research_mode"]
    if operation_id == "get_contracts":
        option_type = data["option_types"][0] if len(data["option_types"]) == 1 else None
        return tuple({
            "underlying": item,
            "expiration_from": data["expiry_from"].date() if data["expiry_from"] else None,
            "expiration_to": data["expiry_to"].date() if data["expiry_to"] else None,
            "option_type": option_type,
            "research_mode": mode,
            "include_expired": True,
            "max_records": 5000,
        } for item in data["underlying_ids"])
    if operation_id == "get_chain_snapshot":
        expiries = tuple(data["expiry_dates"])
        return ({
            "underlying": data["underlying_id"],
            "expiration_date": expiries[0] if len(expiries) == 1 else None,
            "option_type": None,
            "research_mode": mode,
            "executable_only": False,
            "max_records": 5000,
        },)
    if operation_id == "get_quote_history":
        return ({
            "contract_keys": tuple(data["contract_ids"]),
            "start_date": data["start_time"].date(),
            "end_date": data["end_time"].date(),
            "research_mode": mode,
            "max_records_per_contract": 5000,
        },)
    if operation_id == "get_surface_diagnostics":
        return ({
            "underlying": data["underlying_id"],
            "expiration_dates": tuple(data["expiry_dates"]),
            "option_type": None,
            "research_mode": mode,
            "minimum_strikes_per_expiry": data["minimum_quote_count"],
            "executable_only": False,
        },)
    raise KeyError(operation_id)


def build_options_operations(*, inputs: Mapping[str, Any], services: Mapping[str, Any]) -> tuple[ExecutableOperation, ...]:
    if "options_tool_handler_bundle" not in inputs:
        return ()
    boundary = services.get("pit_market_query_port")
    if boundary is None:
        return ()
    manifest = HandlerBundleManifest.model_validate(inputs["options_tool_handler_bundle"], strict=False)
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
                await runtime_bundle.execute("options.observation.v1", _operation_id, arguments, context)
                for arguments in _option_calls(request, _operation_id)
            ]
            return adapt_result(tool_id="options.observation.v1", operation_id=_operation_id, request=request, envelopes=envelopes)

        operations.append(operation(
            inputs=inputs,
            tool_id="options.observation.v1",
            operation_id=operation_id,
            bundle_id=manifest.content_hash,
            qualification_status=statuses.get(("options.observation.v1", operation_id), QualificationStatus.DEGRADED),
            handler=handler,
            context_factory=lambda invocation: canonical_context(invocation, MarketToolCallContext),
            fallback_binding=binding,
        ))
    return tuple(operations)
