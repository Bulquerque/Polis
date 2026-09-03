"""Adapter from P3.S38 company bundles to the generic S40 registry."""
from __future__ import annotations

from collections.abc import Mapping

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.handlers import (
    CompanyHandlerFactory,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.models import (
    CalculateValuationRequest,
    CompanyCallContext,
    CompanyOperationModeQualification,
    CompanyOperationResult,
    CompanyToolBundle,
    GetCapitalAllocationRequest,
    GetFinancialStatementsRequest,
    GetFundamentalSnapshotRequest,
    GetGuidanceRequest,
    GetPeersRequest,
    GetProfileRequest,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.ports import (
    PitResearchQueryPort,
)

from .gateway import GatewayInvocationContext
from .models import QualificationStatus, TransportKind
from .registry import ExecutableOperation, descriptor_from_binding

_REQUEST_MODELS = {
    "get_profile": GetProfileRequest,
    "get_financial_statements": GetFinancialStatementsRequest,
    "get_fundamental_snapshot": GetFundamentalSnapshotRequest,
    "get_guidance": GetGuidanceRequest,
    "get_capital_allocation": GetCapitalAllocationRequest,
    "get_peers": GetPeersRequest,
    "calculate_valuation": CalculateValuationRequest,
}


def _qualification_by_operation(
    qualification: CompanyOperationModeQualification | None,
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
        elif set(statuses) == {"BLOCKED_UPSTREAM"}:
            result[operation_id] = QualificationStatus.BLOCKED_UPSTREAM
        elif "DEGRADED" in statuses or "BLOCKED_UPSTREAM" in statuses:
            result[operation_id] = QualificationStatus.DEGRADED
        else:
            result[operation_id] = QualificationStatus.QUALIFIED_LOCAL
    return result


def build_company_operations(
    *,
    tool_bundle: CompanyToolBundle,
    query_port: PitResearchQueryPort,
    qualification: CompanyOperationModeQualification | None = None,
) -> tuple[ExecutableOperation, ...]:
    handlers = CompanyHandlerFactory(query_port).build()
    statuses = _qualification_by_operation(qualification)
    operations: list[ExecutableOperation] = []
    for binding in tool_bundle.handlers:
        request_model = _REQUEST_MODELS.get(binding.operation_id)
        handler = handlers.get(binding.operation_id)
        if request_model is None or handler is None:
            raise ValueError(f"company operation is missing its public adapter: {binding.operation_id}")
        descriptor = descriptor_from_binding(
            binding,
            tool_id=tool_bundle.tool_id,
            bundle_id=tool_bundle.bundle_hash,
            qualification_status=statuses.get(binding.operation_id, QualificationStatus.DEGRADED),
            transport=TransportKind.COMPOSITE_INTERNAL,
        )

        def context_factory(invocation: GatewayInvocationContext) -> CompanyCallContext:
            return CompanyCallContext(
                request_id=invocation.request_id,
                person_id=invocation.person_id,
                decision_time=invocation.decision_time,
                snapshot_id=invocation.snapshot_id,
                deterministic_seed=invocation.deterministic_seed,
            )

        operations.append(
            ExecutableOperation(
                descriptor=descriptor,
                request_model=request_model,
                result_model=CompanyOperationResult,
                handler=handler.execute,
                context_factory=context_factory,
            )
        )
    return tuple(operations)

# --- Canonical Agent-1 contract adapter ------------------------------------
from typing import Any
from pydantic import BaseModel
from .canonical_support import adapt_result, canonical_context, operation


def _canonical_company_calls(request: BaseModel, operation_id: str) -> tuple[dict[str, Any], ...]:
    data = request.model_dump(mode="python")
    mode = data["research_mode"]
    calls: list[dict[str, Any]] = []
    for entity_id in data.get("entity_ids", ()):
        if operation_id == "get_profile":
            calls.append({"entity_id": entity_id, "research_mode": mode, "view_id": "company_profile", "include_instruments": True, "include_segments": True})
        elif operation_id == "get_financial_statements":
            statement_map = {"BALANCE_SHEET": "BALANCE", "INCOME_STATEMENT": "INCOME", "CASH_FLOW": "CASH_FLOW"}
            calls.append({
                "entity_id": entity_id, "research_mode": mode, "view_id": "financial_statements",
                "statement_types": tuple(statement_map.get(x, x) for x in data["statement_types"]) or ("INCOME", "BALANCE", "CASH_FLOW"),
                "periods": data["period_count"], "include_restated_versions": data["basis"] != "AS_REPORTED",
            })
        elif operation_id == "get_fundamental_snapshot":
            calls.append({"entity_id": entity_id, "research_mode": mode, "view_id": "financial_statements", "periods": data["period_count"], "formula_ids": tuple(data["metrics"])})
        elif operation_id == "get_guidance":
            calls.append({"entity_id": entity_id, "research_mode": mode, "view_id": "company_guidance", "metric_ids": tuple(data["metrics"]), "include_withdrawn": mode == "FORENSIC"})
        elif operation_id == "get_capital_allocation":
            calls.append({"entity_id": entity_id, "research_mode": mode, "statement_view_id": "financial_statements", "corporate_action_view_id": "corporate_actions", "periods": data["period_count"]})
        elif operation_id == "get_peers":
            calls.append({"entity_id": entity_id, "research_mode": mode, "view_id": "company_peers", "maximum_peers": data["max_peers"], "authority_classes": ("DOCUMENTED", "CANONICAL")})
        elif operation_id == "calculate_valuation":
            method_map = {"MULTIPLES": "OBSERVED_MULTIPLES", "HISTORICAL_BANDS": "HISTORICAL_BAND", "PEER_BANDS": "PEER_BAND", "SCENARIO_DCF": "SCENARIO_DCF", "REVERSE_DCF": "REVERSE_DCF"}
            assumptions = dict(data["assumptions"])
            call = {
                "entity_id": entity_id, "research_mode": mode, "method": method_map[data["method"]],
                "fundamentals_view_id": "financial_statements", "peers_view_id": "company_peers", "market_view_id": "market_prices",
                "multiple_name": str(assumptions.get("multiple_name", "EV_EBITDA")),
                "explicit_multiple": assumptions.get("explicit_multiple"), "metric_value": assumptions.get("metric_value"),
                "dcf": assumptions.get("dcf"), "reverse_dcf": assumptions.get("reverse_dcf"),
            }
            calls.append(call)
        else:
            raise KeyError(operation_id)
    return tuple(calls)


def build_canonical_company_operations(
    *,
    inputs: Mapping[str, Any],
    query_port: PitResearchQueryPort,
) -> tuple[ExecutableOperation, ...]:
    tool_bundle = CompanyToolBundle.model_validate(inputs["company_tool_handler_bundle"], strict=False)
    qualification = None
    if inputs.get("company_operation_mode_qualification") is not None:
        qualification = CompanyOperationModeQualification.model_validate(inputs["company_operation_mode_qualification"], strict=False)
    handlers = CompanyHandlerFactory(query_port).build()
    statuses = _qualification_by_operation(qualification)
    operations: list[ExecutableOperation] = []
    for binding in tool_bundle.handlers:
        operation_id = binding.operation_id
        family_handler = handlers.get(operation_id)
        if family_handler is None:
            raise ValueError(f"company operation missing handler: {operation_id}")

        async def handler(request: BaseModel, context: CompanyCallContext, *, _operation_id: str = operation_id, _handler=family_handler) -> BaseModel:
            envelopes = []
            request_type = _REQUEST_MODELS[_operation_id]
            for arguments in _canonical_company_calls(request, _operation_id):
                family_request = request_type.model_validate(arguments, strict=False)
                envelopes.append(await _handler.execute(family_request, context))
            return adapt_result(tool_id="company.fundamentals.v1", operation_id=_operation_id, request=request, envelopes=envelopes)

        operations.append(operation(
            inputs=inputs,
            tool_id="company.fundamentals.v1",
            operation_id=operation_id,
            bundle_id=tool_bundle.bundle_hash,
            qualification_status=statuses.get(operation_id, QualificationStatus.DEGRADED),
            handler=handler,
            context_factory=lambda invocation: canonical_context(invocation, CompanyCallContext),
            fallback_binding=binding,
        ))
    return tuple(operations)
