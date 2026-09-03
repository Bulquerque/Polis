from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.gateway import CompositeResearchToolGateway
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.models import AliasBinding, TransportKind
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.registry import OperationRegistry
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    RequestValidationStatus,
    ToolCallRequestRecord,
    ToolExecutionStatus,
    ValidatedToolCallRequestRecord,
)

from ._fixtures import echo_operation


def request(*, tool_id: str = "test.echo.v1", operation_id: str = "echo", arguments=None):
    raw = ToolCallRequestRecord(
        tool_call_request_id="req-1",
        cognition_transaction_id="tx-1",
        person_id="person-1",
        tool_id=tool_id,
        operation_id=operation_id,
        arguments=arguments or {"text": "hello", "research_mode": "BASIC"},
        reason="test",
        expected_information_gain=0.5,
        requested_at=datetime(2024, 1, 10, tzinfo=UTC),
        as_of=datetime(2024, 1, 10, tzinfo=UTC),
        idempotency_key="idem-1",
    )
    return ValidatedToolCallRequestRecord(
        request=raw,
        validation_status=RequestValidationStatus.ACCEPTED,
        provider_id="internal_research",
        entitlement_version="v1",
        arguments_schema={},
        result_schema={},
        read_only=True,
        point_in_time_safe=True,
    )


@pytest.mark.asyncio
async def test_gateway_executes_strict_internal_operation():
    gateway = CompositeResearchToolGateway(
        registry=OperationRegistry((echo_operation(),)),
        snapshot_id="snapshot-1",
        execution_profile="TEST",
    )
    result = await gateway.execute(request())
    assert result.status is ToolExecutionStatus.SUCCEEDED
    assert result.canonical_payload["metrics"]["text"] == "hello"
    assert result.available_at == datetime(2024, 1, 10, tzinfo=UTC)


@pytest.mark.asyncio
async def test_gateway_resolves_alias_without_second_handler():
    alias = AliasBinding(
        alias_tool_id="legacy.echo.v1",
        alias_operation_id="run",
        target_tool_id="test.echo.v1",
        target_operation_id="echo",
        fixed_arguments={"research_mode": "BASIC"},
    )
    gateway = CompositeResearchToolGateway(
        registry=OperationRegistry((echo_operation(),), (alias,)),
        snapshot_id="snapshot-1",
        execution_profile="TEST",
    )
    result = await gateway.execute(
        request(tool_id="legacy.echo.v1", operation_id="run", arguments={"text": "alias"})
    )
    assert result.status is ToolExecutionStatus.SUCCEEDED
    assert result.canonical_payload["metrics"]["text"] == "alias"


@pytest.mark.asyncio
async def test_gateway_rejects_invalid_arguments():
    gateway = CompositeResearchToolGateway(
        registry=OperationRegistry((echo_operation(),)),
        snapshot_id="snapshot-1",
        execution_profile="TEST",
    )
    result = await gateway.execute(request(arguments={"unknown": True}))
    assert result.status is ToolExecutionStatus.FAILED_SCHEMA
    assert result.error.code == "P3RT-CONTRACT-REQUEST-SCHEMA-INVALID"


@pytest.mark.asyncio
async def test_gateway_blocks_network_transport_in_backtest():
    gateway = CompositeResearchToolGateway(
        registry=OperationRegistry((echo_operation(transport=TransportKind.MCP_OPTIONAL),)),
        snapshot_id="snapshot-1",
        execution_profile="REPLAY",
    )
    result = await gateway.execute(request())
    assert result.status is ToolExecutionStatus.REJECTED_AUTHORIZATION
    assert result.error.code == "P3RT-RUNTIME-NETWORK-FORBIDDEN-IN-BACKTEST"


def test_registry_rejects_duplicate_operations():
    with pytest.raises(ValueError, match="duplicate operation"):
        OperationRegistry((echo_operation(), echo_operation()))
