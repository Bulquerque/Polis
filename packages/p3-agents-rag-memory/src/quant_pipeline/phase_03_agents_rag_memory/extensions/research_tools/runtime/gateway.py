"""Composite internal gateway implementing the existing S21 ToolGatewayPort."""
from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping

from pydantic import BaseModel, ValidationError

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash, utc
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    RequestValidationStatus,
    ToolErrorRecord,
    ToolExecutionResponse,
    ToolExecutionStatus,
    ValidatedToolCallRequestRecord,
)

from .models import OperationDescriptor, TransportKind
from .registry import AliasResolution, ExecutableOperation, OperationRegistry
from .gateway_support import (
    GatewayInvocationContext, InMemoryTraceSink, PreparedInvocation, TraceSinkPort,
    available_at, cost_units, evidence_ids, failure_code, failure_status,
    trace_id, trace_record, validate_result,
)


class CompositeResearchToolGateway:
    """Validate, dispatch and map internal research handlers to S21 responses."""

    _NETWORK_TRANSPORTS = {TransportKind.MCP_OPTIONAL, TransportKind.HTTP_OPTIONAL}

    def __init__(
        self,
        *,
        registry: OperationRegistry,
        snapshot_id: str,
        execution_profile: str,
        deterministic_seed: int = 0,
        timeout_seconds: float = 30.0,
        trace_sink: TraceSinkPort | None = None,
    ) -> None:
        if timeout_seconds <= 0.0 or timeout_seconds > 120.0:
            raise ValueError("timeout_seconds must be in (0, 120]")
        self._registry = registry
        self._snapshot_id = snapshot_id
        self._execution_profile = execution_profile.upper()
        self._deterministic_seed = deterministic_seed
        self._timeout_seconds = timeout_seconds
        self._trace_sink = trace_sink or InMemoryTraceSink()

    def discover(self) -> tuple[OperationDescriptor, ...]:
        """Expose callable local capabilities from the dispatch registry."""
        return self._registry.discoverable_operations()

    async def execute(self, request: ValidatedToolCallRequestRecord) -> ToolExecutionResponse:
        prepared = self._prepare(request)
        if isinstance(prepared, ToolExecutionResponse):
            return prepared
        self._trace("tool.handler.started", prepared.trace_id, request, prepared.operation)
        result = await self._invoke(prepared, request)
        if isinstance(result, ToolExecutionResponse):
            return result
        return self._success(prepared, request, result)

    def _prepare(
        self, request: ValidatedToolCallRequestRecord
    ) -> PreparedInvocation | ToolExecutionResponse:
        accepted = self._require_accepted(request)
        if accepted is not None:
            return accepted
        resolved = self._resolve(request)
        if isinstance(resolved, ToolExecutionResponse):
            return resolved
        operation, resolution = resolved
        provider_id = request.provider_id or operation.descriptor.provider_id
        rejected = self._authorize_transport(request, operation, provider_id)
        if rejected is not None:
            return rejected
        parsed = self._parse_request(operation, resolution.arguments, provider_id)
        if isinstance(parsed, ToolExecutionResponse):
            return parsed
        return PreparedInvocation(
            operation=operation,
            resolution=resolution,
            provider_id=provider_id,
            parsed_request=parsed,
            context=self._invocation_context(request),
            trace_id=trace_id(request, operation),
        )

    @staticmethod
    def _require_accepted(request: ValidatedToolCallRequestRecord) -> ToolExecutionResponse | None:
        if request.validation_status is RequestValidationStatus.ACCEPTED:
            return None
        return CompositeResearchToolGateway._failure(
            provider_id=request.provider_id or "internal_research",
            status=ToolExecutionStatus.REJECTED_AUTHORIZATION,
            code="P3RT-AUTH-REQUEST-NOT-ACCEPTED",
            message="gateway received a non-accepted request",
        )

    def _resolve(
        self, request: ValidatedToolCallRequestRecord
    ) -> tuple[ExecutableOperation, AliasResolution] | ToolExecutionResponse:
        try:
            operation, resolution = self._registry.resolve(
                request.request.tool_id,
                request.request.operation_id,
                request.request.arguments,
            )
            return operation, resolution
        except (KeyError, ValueError) as exc:
            is_alias_conflict = isinstance(exc, ValueError)
            return self._failure(
                provider_id=request.provider_id or "internal_research",
                status=(
                    ToolExecutionStatus.FAILED_SCHEMA
                    if is_alias_conflict
                    else ToolExecutionStatus.FAILED_PROVIDER
                ),
                code=(
                    "P3RT-ALIAS-FIXED-ARGUMENT-CONFLICT"
                    if is_alias_conflict
                    else "P3RT-HANDLER-NOT-REGISTERED"
                ),
                message=str(exc),
            )

    def _authorize_transport(
        self,
        request: ValidatedToolCallRequestRecord,
        operation: ExecutableOperation,
        provider_id: str,
    ) -> ToolExecutionResponse | None:
        if provider_id != operation.descriptor.provider_id:
            return self._failure(
                provider_id=provider_id,
                status=ToolExecutionStatus.REJECTED_AUTHORIZATION,
                code="P3RT-AUTH-PROVIDER-MISMATCH",
                message="authorized provider differs from operation provider",
            )
        if self._network_forbidden(operation):
            return self._failure(
                provider_id=provider_id,
                status=ToolExecutionStatus.REJECTED_AUTHORIZATION,
                code="P3RT-RUNTIME-NETWORK-FORBIDDEN-IN-BACKTEST",
                message="network transport is disabled outside LIVE execution",
            )
        return None

    @staticmethod
    def _parse_request(
        operation: ExecutableOperation,
        arguments: Mapping[str, object],
        provider_id: str,
    ) -> BaseModel | ToolExecutionResponse:
        try:
            payload = json.dumps(dict(arguments), sort_keys=True, separators=(",", ":"))
            return operation.request_model.model_validate_json(payload)
        except (ValidationError, TypeError, ValueError) as exc:
            return CompositeResearchToolGateway._failure(
                provider_id=provider_id,
                status=ToolExecutionStatus.FAILED_SCHEMA,
                code="P3RT-CONTRACT-REQUEST-SCHEMA-INVALID",
                message=str(exc),
            )

    def _invocation_context(self, request: ValidatedToolCallRequestRecord) -> GatewayInvocationContext:
        transaction_id = request.request.cognition_transaction_id
        return GatewayInvocationContext(
            request_id=request.request.tool_call_request_id,
            person_id=request.request.person_id,
            run_id=transaction_id,
            cycle_id=transaction_id,
            cognition_transaction_id=transaction_id,
            decision_time=utc(request.request.as_of),
            snapshot_id=self._snapshot_id,
            deterministic_seed=self._deterministic_seed,
            execution_profile=self._execution_profile,
        )

    async def _invoke(
        self,
        prepared: PreparedInvocation,
        request: ValidatedToolCallRequestRecord,
    ) -> BaseModel | ToolExecutionResponse:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                raw = await prepared.operation.handler(
                    prepared.parsed_request,
                    prepared.operation.context_factory(prepared.context),
                )
            result = validate_result(prepared.operation, raw)
            if available_at(
                result.model_dump(mode="json"), request.request.as_of
            ) > utc(request.request.as_of):
                return self._failure(
                    provider_id=prepared.provider_id,
                    status=ToolExecutionStatus.REJECTED_TEMPORAL,
                    code="P3RT-PIT-RESULT-AVAILABLE-AFTER-AS-OF",
                    message="handler result is not available at the request as_of",
                )
            return result
        except TimeoutError:
            return self._invoke_failure(prepared, request, "timeout")
        except ValidationError as exc:
            return self._invoke_failure(prepared, request, "result_invalid", exc)
        except Exception as exc:  # adapter boundary: preserve failure, never fake success
            return self._invoke_failure(prepared, request, "failed", exc)

    def _invoke_failure(
        self,
        prepared: PreparedInvocation,
        request: ValidatedToolCallRequestRecord,
        kind: str,
        exc: Exception | None = None,
    ) -> ToolExecutionResponse:
        self._trace(f"tool.handler.{kind}", prepared.trace_id, request, prepared.operation)
        if kind == "timeout":
            return self._failure(
                provider_id=prepared.provider_id,
                status=ToolExecutionStatus.FAILED_TIMEOUT,
                code="P3RT-RUNTIME-HANDLER-TIMEOUT",
                message="handler exceeded the configured timeout",
            )
        assert exc is not None
        if kind == "result_invalid":
            return self._failure(
                provider_id=prepared.provider_id,
                status=ToolExecutionStatus.FAILED_SCHEMA,
                code="P3RT-HANDLER-RESULT-SCHEMA-INVALID",
                message=str(exc),
            )
        return self._failure(
            provider_id=prepared.provider_id,
            status=failure_status(exc),
            code=failure_code(exc),
            message=str(exc),
        )

    def _success(
        self,
        prepared: PreparedInvocation,
        request: ValidatedToolCallRequestRecord,
        result: BaseModel,
    ) -> ToolExecutionResponse:
        payload = result.model_dump(mode="json")
        response_hash = content_hash(payload)
        evidence_refs = evidence_ids(payload)
        self._trace(
            "tool.handler.completed",
            prepared.trace_id,
            request,
            prepared.operation,
            attributes={
                "response_hash": response_hash,
                "alias_applied": prepared.resolution.alias_applied,
                "evidence_count": len(evidence_refs),
            },
        )
        return ToolExecutionResponse(
            status=ToolExecutionStatus.SUCCEEDED,
            provider_id=prepared.provider_id,
            canonical_payload=payload,
            available_at=available_at(payload, request.request.as_of),
            cost_units=cost_units(payload),
            response_hash=response_hash,
            evidence_refs=evidence_refs,
        )

    def _network_forbidden(self, operation: ExecutableOperation) -> bool:
        return self._execution_profile != "LIVE" and operation.descriptor.transport in self._NETWORK_TRANSPORTS

    @staticmethod
    def _failure(
        *, provider_id: str, status: ToolExecutionStatus, code: str,
        message: str, retryable: bool = False,
    ) -> ToolExecutionResponse:
        return ToolExecutionResponse(
            status=status,
            provider_id=provider_id,
            error=ToolErrorRecord(code=code, message=message, retryable=retryable),
        )

    def _trace(
        self, event_name: str, trace: str, request: ValidatedToolCallRequestRecord,
        operation: ExecutableOperation, attributes: Mapping[str, object] | None = None,
    ) -> None:
        self._trace_sink.emit(trace_record(event_name, trace, request, operation, attributes))
