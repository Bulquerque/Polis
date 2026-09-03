"""Adapter from the P3.S39 public bundle to the generic S40 registry."""
from __future__ import annotations

from collections.abc import Mapping

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.handlers import (
    QuantHandlerFactory,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.models import (
    CorrelationRequest,
    DrawdownRequest,
    EntropyRequest,
    EventWindowRequest,
    QuantCallContext,
    QuantOperationModeQualification,
    QuantOperationResult,
    QuantToolBundle,
    RealizedVolatilityRequest,
    ReturnStatisticsRequest,
    ScenarioShockRequest,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.ports import (
    PitResearchQueryPort,
)

from .gateway import GatewayInvocationContext
from .models import QualificationStatus, TransportKind
from .registry import ExecutableOperation, descriptor_from_binding

_REQUEST_MODELS = {
    "return_statistics": ReturnStatisticsRequest,
    "realized_volatility": RealizedVolatilityRequest,
    "drawdown": DrawdownRequest,
    "correlation": CorrelationRequest,
    "entropy": EntropyRequest,
    "event_window": EventWindowRequest,
    "scenario_shock": ScenarioShockRequest,
}


def _qualification_by_operation(
    qualification: QuantOperationModeQualification | None,
) -> Mapping[str, QualificationStatus]:
    if qualification is None:
        return {}
    grouped: dict[str, list[str]] = {}
    for record in qualification.records:
        grouped.setdefault(record.operation_id, []).append(record.status.value)
    result: dict[str, QualificationStatus] = {}
    for operation_id, statuses in grouped.items():
        if "FAILED" in statuses:
            result[operation_id] = QualificationStatus.FAILED
        elif "BLOCKED_UPSTREAM" in statuses:
            result[operation_id] = QualificationStatus.BLOCKED_UPSTREAM
        elif "DEGRADED" in statuses:
            result[operation_id] = QualificationStatus.DEGRADED
        else:
            result[operation_id] = QualificationStatus.QUALIFIED_LOCAL
    return result


def build_quant_operations(
    *,
    tool_bundle: QuantToolBundle,
    query_port: PitResearchQueryPort,
    qualification: QuantOperationModeQualification | None = None,
) -> tuple[ExecutableOperation, ...]:
    handlers = QuantHandlerFactory(query_port).build()
    statuses = _qualification_by_operation(qualification)
    operations: list[ExecutableOperation] = []
    for binding in tool_bundle.handlers:
        request_model = _REQUEST_MODELS.get(binding.operation_id)
        handler = handlers.get(binding.operation_id)
        if request_model is None or handler is None:
            raise ValueError(f"quant operation is missing its public adapter: {binding.operation_id}")
        descriptor = descriptor_from_binding(
            binding,
            tool_id=tool_bundle.tool_id,
            bundle_id=tool_bundle.bundle_hash,
            qualification_status=statuses.get(
                binding.operation_id,
                QualificationStatus.DEGRADED,
            ),
            transport=TransportKind.COMPOSITE_INTERNAL,
        )

        def context_factory(
            invocation: GatewayInvocationContext,
            *,
            _request_id: str | None = None,
        ) -> QuantCallContext:
            return QuantCallContext(
                request_id=_request_id or invocation.request_id,
                person_id=invocation.person_id,
                decision_time=invocation.decision_time,
                snapshot_id=invocation.snapshot_id,
                deterministic_seed=invocation.deterministic_seed,
            )

        operations.append(
            ExecutableOperation(
                descriptor=descriptor,
                request_model=request_model,
                result_model=QuantOperationResult,
                handler=handler.execute,
                context_factory=context_factory,
            )
        )
    return tuple(operations)

# --- Canonical Agent-1 contract adapter ------------------------------------
import math
import statistics
from typing import Any
from pydantic import BaseModel
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.contracts.operation_models import RealizedVolatilityResult
from .canonical_support import adapt_result, canonical_context, operation


def _canonical_quant_calls(request: BaseModel, operation_id: str) -> tuple[dict[str, Any], ...]:
    data = request.model_dump(mode="python")
    mode = data["research_mode"]
    if operation_id == "return_statistics":
        return tuple({
            "start_time": data["start_time"], "end_time": data["end_time"], "instrument_id": item,
            "view_id": "market_returns", "research_mode": mode, "return_kind": "SIMPLE",
            "quantiles": (0.05, 0.5, 0.95), "trim_fraction": 0.0, "annualization_factor": 252.0,
        } for item in data["instrument_ids"])
    if operation_id == "realized_volatility":
        return tuple({
            "start_time": data["start_time"], "end_time": data["end_time"], "instrument_id": item,
            "view_id": "market_returns", "research_mode": mode, "estimators": (data["estimator"],),
            "annualization_factor": data["annualization_factor"], "bootstrap_samples": 0,
            "bootstrap_confidence": 0.95, "block_length": 5,
        } for item in data["instrument_ids"])
    if operation_id == "drawdown":
        return tuple({
            "start_time": data["start_time"], "end_time": data["end_time"], "instrument_id": item,
            "view_id": "market_returns", "research_mode": mode, "wealth_start": 1.0,
        } for item in data["instrument_ids"])
    if operation_id == "correlation":
        return ({
            "start_time": data["start_time"], "end_time": data["end_time"],
            "left_instrument_id": data["instrument_ids"][0], "right_instrument_id": data["instrument_ids"][1],
            "view_id": "market_returns", "research_mode": mode, "method": data["method"],
            "return_kind": "SIMPLE", "min_observations": 3, "bootstrap_samples": 0,
            "bootstrap_confidence": 0.95, "block_length": 5,
        },)
    if operation_id == "entropy":
        return tuple({
            "start_time": data["start_time"], "end_time": data["end_time"], "instrument_id": item,
            "view_id": "market_returns", "research_mode": mode, "method": data["method"],
            "input_return_kind": "SIMPLE", "binning_policy": "EQUAL_WIDTH", "bins": data["bins"] or 10,
            "fixed_edges": (), "embedding_dimension": 3, "delay": 1, "normalize": True,
            "bootstrap_samples": 0, "bootstrap_confidence": 0.95, "block_length": 5,
        } for item in data["instrument_ids"])
    if operation_id == "event_window":
        calls=[]
        for event_id in data["event_ids"]:
            for instrument_id in data["instrument_ids"]:
                calls.append({
                    "event_id": event_id, "instrument_id": instrument_id, "event_view_id": "events",
                    "market_view_id": "market_prices", "benchmark_id": data["benchmark_id"],
                    "benchmark_view_id": "market_prices", "research_mode": mode,
                    "adjustment": "BENCHMARK" if data["benchmark_id"] else "NONE",
                    "pre_window": data["pre_observations"], "post_window": data["post_observations"],
                    "return_kind": "SIMPLE", "placebo_offsets": (),
                })
        return tuple(calls)
    if operation_id == "scenario_shock":
        return ({
            "scenario_id": "canonical_scenario", "research_mode": mode, "baseline_value": 0.0,
            "factor_shocks": dict(data["shocks"]), "linear_exposures": dict(data["exposures"]),
            "quadratic_exposures": (), "sensitivity_multipliers": (0.5, 1.0, 1.5),
        },)
    raise KeyError(operation_id)


def build_canonical_quant_operations(
    *,
    inputs: Mapping[str, Any],
    query_port: PitResearchQueryPort,
) -> tuple[ExecutableOperation, ...]:
    tool_bundle = QuantToolBundle.model_validate(inputs["quant_tool_handler_bundle"], strict=False)
    qualification = None
    if inputs.get("quant_operation_mode_qualification") is not None:
        qualification = QuantOperationModeQualification.model_validate(inputs["quant_operation_mode_qualification"], strict=False)
    handlers = QuantHandlerFactory(query_port).build()
    statuses = _qualification_by_operation(qualification)
    operations: list[ExecutableOperation] = []
    for binding in tool_bundle.handlers:
        operation_id = binding.operation_id
        family_handler = handlers.get(operation_id)
        if family_handler is None:
            raise ValueError(f"quant operation missing handler: {operation_id}")

        async def handler(request: BaseModel, context: QuantCallContext, *, _operation_id: str = operation_id, _handler=family_handler) -> BaseModel:
            if _operation_id == "realized_volatility" and request.returns:
                values = tuple(float(value) for value in request.returns)
                volatility = statistics.pstdev(values) * math.sqrt(float(request.annualization_factor)) if len(values) > 1 else 0.0
                return RealizedVolatilityResult(
                    records=(), truncated=False, warnings=(),
                    realized_volatility=volatility, estimator=request.estimator,
                )
            envelopes = []
            request_type = _REQUEST_MODELS[_operation_id]
            for arguments in _canonical_quant_calls(request, _operation_id):
                family_request = request_type.model_validate(arguments, strict=False)
                envelopes.append(await _handler.execute(family_request, context))
            return adapt_result(tool_id="quant.diagnostics.v1", operation_id=_operation_id, request=request, envelopes=envelopes)

        operations.append(operation(
            inputs=inputs,
            tool_id="quant.diagnostics.v1",
            operation_id=operation_id,
            bundle_id=tool_bundle.bundle_hash,
            qualification_status=statuses.get(operation_id, QualificationStatus.DEGRADED),
            handler=handler,
            context_factory=lambda invocation: canonical_context(invocation, QuantCallContext),
            fallback_binding=binding,
        ))
    return tuple(operations)
