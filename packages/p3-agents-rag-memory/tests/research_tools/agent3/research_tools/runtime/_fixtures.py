from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import JsonValue

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import ContractModel, content_hash
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.gateway import GatewayInvocationContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.models import (
    OperationDescriptor,
    QualificationStatus,
    TransportKind,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.registry import ExecutableOperation

DT = datetime(2024, 1, 10, tzinfo=UTC)


class EchoRequest(ContractModel):
    text: str
    research_mode: str = "BASIC"


class EchoResult(ContractModel):
    tool_id: str = "test.echo.v1"
    operation_id: str = "echo"
    requested_mode: str
    executed_mode: str
    outcome_status: str
    metrics: dict[str, JsonValue]
    evidence_refs: tuple[dict[str, JsonValue], ...] = ()
    coverage: dict[str, JsonValue]
    latest_available_at: datetime
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EchoContext:
    decision_time: datetime


async def echo_handler(request: EchoRequest, context: EchoContext) -> EchoResult:
    return EchoResult(
        requested_mode=request.research_mode,
        executed_mode=request.research_mode,
        outcome_status="PASS",
        metrics={"text": request.text},
        coverage={
            "score": 1.0,
            "observations_requested": 1,
            "observations_used": 1,
            "observations_rejected_future": 0,
            "observations_rejected_quality": 0,
            "missing_requirements": [],
        },
        latest_available_at=context.decision_time,
    )


def echo_operation(*, transport: TransportKind = TransportKind.LOCAL_FUNCTION) -> ExecutableOperation:
    descriptor = OperationDescriptor(
        tool_id="test.echo.v1",
        operation_id="echo",
        handler_id="test.echo.handler.v1",
        handler_version="1.0.0",
        provider_id="internal_research",
        transport=transport,
        request_schema_ref="test/echo_request.schema.json",
        result_schema_ref="test/echo_result.schema.json",
        supported_modes=("BASIC",),
        qualification_status=QualificationStatus.QUALIFIED_LOCAL,
        source_bundle_id="test.echo.bundle.v1",
    )
    return ExecutableOperation(
        descriptor=descriptor,
        request_model=EchoRequest,
        result_model=EchoResult,
        handler=echo_handler,
        context_factory=lambda invocation: EchoContext(invocation.decision_time),
    )


class InMemoryQueryPort:
    def __init__(self) -> None:
        self.rows = (
            self._row("A-1", "2024-01-01T16:00:00Z", 100.0),
            self._row("A-2", "2024-01-02T16:00:00Z", 105.0),
            self._row("A-3", "2024-01-03T16:00:00Z", 103.0),
            self._row("A-future", "2024-01-12T16:00:00Z", 120.0),
        )

    @staticmethod
    def _row(record_id: str, available_at: str, close: float) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "record_id": record_id,
            "source_id": "fixture-market",
            "artifact_id": "fixture-market-artifact",
            "available_at": available_at,
            "instrument_id": "A",
            "observation_time": available_at,
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "source_quality": 0.95,
        }
        payload["content_hash"] = content_hash(payload)
        return payload

    async def query(
        self,
        *,
        view_id: str,
        filters: Mapping[str, JsonValue],
        decision_time: datetime,
    ) -> Sequence[Mapping[str, JsonValue]]:
        del view_id, decision_time
        instrument = filters.get("instrument_id")
        return tuple(row for row in self.rows if instrument is None or row.get("instrument_id") == instrument)
