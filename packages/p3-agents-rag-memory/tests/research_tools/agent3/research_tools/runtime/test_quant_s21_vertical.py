from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from quant_pipeline.phase_03_agents_rag_memory.contracts.execution import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.assembly import (
    execute_m01,
    execute_m02,
    execute_m03,
    execute_m04,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.models import (
    QuantOperationModeQualification,
    QuantToolBundle,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.gateway import CompositeResearchToolGateway
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.quant_adapter import build_quant_operations
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.registry import OperationRegistry
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    RequestValidationStatus,
    ToolCallRequestRecord,
    ToolExecutionStatus,
    ValidatedToolCallRequestRecord,
)

from ._fixtures import InMemoryQueryPort


async def quant_bundle():
    context = ModuleExecutionContext()
    base = {"research_data_boundary_bundle": {}, "tool_operation_registry": {}, "research_mode_registry": {}}
    m1 = execute_m01({**base, "quant_method_policy_config": {}, "frequency_annualization_registry": {}}, context)
    m2 = execute_m02({**base, "dependence_method_policy_config": {}, "entropy_discretization_registry": {}}, context)
    m3 = execute_m03({**base, "event_scenario_method_policy_config": {}}, context)
    m4 = execute_m04(
        {
            **m1,
            **m2,
            **m3,
            "quant_contract_test_report": {"status": "PASS", "passed": 1},
            "quant_property_test_report": {"status": "PASS", "passed": 1},
            "quant_leakage_test_report": {"status": "PASS", "passed": 1},
        },
        context,
    )
    return (
        QuantToolBundle.model_validate(m4["quant_tool_handler_bundle"], strict=False),
        QuantOperationModeQualification.model_validate(m4["quant_operation_mode_qualification"], strict=False),
    )


@pytest.mark.asyncio
async def test_actual_s39_handler_runs_through_s40_gateway():
    bundle, qualification = await quant_bundle()
    operations = build_quant_operations(
        tool_bundle=bundle,
        query_port=InMemoryQueryPort(),
        qualification=qualification,
    )
    gateway = CompositeResearchToolGateway(
        registry=OperationRegistry(operations),
        snapshot_id="snapshot-1",
        execution_profile="REPLAY",
        deterministic_seed=7,
    )
    raw = ToolCallRequestRecord(
        tool_call_request_id="req-quant",
        cognition_transaction_id="tx-quant",
        person_id="person-1",
        tool_id="quant.diagnostics.v1",
        operation_id="return_statistics",
        arguments={
            "instrument_id": "A",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-09T23:59:59Z",
            "research_mode": "BASIC",
        },
        reason="diagnostic",
        expected_information_gain=0.5,
        requested_at=datetime(2024, 1, 10, tzinfo=UTC),
        as_of=datetime(2024, 1, 10, tzinfo=UTC),
        idempotency_key="idem-quant",
    )
    validated = ValidatedToolCallRequestRecord(
        request=raw,
        validation_status=RequestValidationStatus.ACCEPTED,
        provider_id="internal_research",
        entitlement_version="v1",
        arguments_schema={},
        result_schema={},
        read_only=True,
        point_in_time_safe=True,
    )
    response = await gateway.execute(validated)
    assert response.status is ToolExecutionStatus.SUCCEEDED
    assert response.canonical_payload["operation_id"] == "return_statistics"
    assert response.canonical_payload["coverage"]["observations_rejected_future"] == 1
    assert response.evidence_refs
