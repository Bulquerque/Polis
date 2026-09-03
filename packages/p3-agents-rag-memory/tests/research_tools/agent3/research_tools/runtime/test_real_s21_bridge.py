from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.gateway import CompositeResearchToolGateway
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.registry import OperationRegistry
from quant_pipeline.phase_03_agents_rag_memory.runtime.tooling import execute_tool_requests, validate_tool_results
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    ArtifactStatus,
    CognitionConfig,
    ExecutionMode,
    LineageRecord,
    MCPGatewayPolicy,
    PersonToolEntitlementPanel,
    Phase3RunSnapshot,
    ProviderAdapterRegistryConfig,
    ProviderModelConfig,
    RequestValidationStatus,
    RetrievalEvidenceMap,
    ToolCallAuditContract,
    ToolCallRequestRecord,
    ToolOperationEntitlement,
    ToolProviderConfig,
    ToolResultValidationStatus,
    ValidatedToolCallRequestPanel,
    ValidatedToolCallRequestRecord,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_ports import S21Runtime
from quant_pipeline.phase_03_agents_rag_memory.adapters.s21_reference import FixedClock

from ._fixtures import EchoRequest, EchoResult, echo_operation


class UnusedPort:
    pass


def lineage(module: str) -> LineageRecord:
    return LineageRecord(lineage_id=f"{module}:lineage", producer_module_id=module)


@pytest.mark.asyncio
async def test_s40_gateway_runs_inside_real_s21_m03_and_validates_in_m04():
    decision = datetime(2024, 1, 10, tzinfo=UTC)
    gateway = CompositeResearchToolGateway(
        registry=OperationRegistry((echo_operation(),)),
        snapshot_id="snapshot-1",
        execution_profile="REPLAY",
    )
    runtime = S21Runtime(
        llm=UnusedPort(),
        tool_gateway=gateway,
        clock=FixedClock(decision),
        prompts=UnusedPort(),
    )
    request = ToolCallRequestRecord(
        tool_call_request_id="req-real-s21",
        cognition_transaction_id="tx-real-s21",
        person_id="person-1",
        tool_id="test.echo.v1",
        operation_id="echo",
        arguments={"text": "through-s21", "research_mode": "BASIC"},
        reason="integration",
        expected_information_gain=0.5,
        requested_at=decision,
        as_of=decision,
        idempotency_key="idem-real-s21",
    )
    validated = ValidatedToolCallRequestRecord(
        request=request,
        validation_status=RequestValidationStatus.ACCEPTED,
        provider_id="internal_research",
        entitlement_version="v1",
        arguments_schema=EchoRequest.model_json_schema(),
        result_schema=EchoResult.model_json_schema(),
        read_only=True,
        point_in_time_safe=True,
    )
    output = await execute_tool_requests(
        validated_requests=ValidatedToolCallRequestPanel(
            status=ArtifactStatus.READY,
            records=(validated,),
            lineage=lineage("P3.S21.M02"),
        ),
        gateway_policy=MCPGatewayPolicy(
            policy_version="v1",
            cache_mode="replay_only",
            max_retry_attempts=0,
        ),
        audit_contract=ToolCallAuditContract(
            contract_version="v1",
            required_fields=("audit_id", "tool_call_request_id", "execution_id"),
            redact_fields=("arguments",),
        ),
        provider_registry=ProviderAdapterRegistryConfig(
            providers=(
                ProviderModelConfig(
                    provider_id="llm-fixture",
                    model_id="fixture",
                    supports_structured_output=True,
                    supports_seed=True,
                    max_context_tokens=4096,
                    max_output_tokens=512,
                ),
            ),
            tool_providers=(ToolProviderConfig(provider_id="internal_research", max_concurrency=1),),
            selected_provider_id="llm-fixture",
            selected_model_id="fixture",
        ),
        runtime=runtime,
    )
    raw = output["raw_tool_result_panel"]
    audits = output["tool_call_audit_panel"]
    assert raw.records[0].canonical_payload["metrics"]["text"] == "through-s21"
    assert raw.records[0].evidence_refs == (f"tool:{raw.records[0].execution_id}",)
    result = validate_tool_results(
        raw_results=raw,
        audit_panel=audits,
        snapshot=Phase3RunSnapshot(
            run_id="run-1",
            cycle_id="cycle-1",
            snapshot_id="snapshot-1",
            as_of=decision,
            execution_mode=ExecutionMode.REPLAY,
            configuration_hash="f" * 64,
        ),
        retrieval_evidence=RetrievalEvidenceMap(
            status=ArtifactStatus.EMPTY_VALID,
            records=(),
            lineage=lineage("P3.S20.M05"),
        ),
    )
    assert result.records[0].validation_status is ToolResultValidationStatus.VALID
