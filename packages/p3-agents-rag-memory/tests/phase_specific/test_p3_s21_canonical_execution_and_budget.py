from __future__ import annotations

import pytest

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S21_M01_initial_llm_cognition_planner import execute
from quant_pipeline.phase_03_agents_rag_memory.runtime.cognition import plan_initial_cognition
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_errors import S21ContractError

from .p3_s21_factories import cognition_config, context_bundle, provider_registry, runtime


@pytest.mark.asyncio
async def test_m01_runs_through_canonical_module_context():
    inputs = {
        "validated_person_context_bundle": context_bundle().model_dump(mode="json"),
        "cognition_config": cognition_config().model_dump(mode="json"),
        "provider_adapter_registry_config": provider_registry().model_dump(mode="json"),
    }
    result = await execute(inputs, ModuleExecutionContext(services={"runtime": runtime()}))
    assert result["tool_call_request_panel"]["records"][0]["tool_id"] == "market_lookup"


@pytest.mark.asyncio
async def test_initial_cognition_rejects_tool_requests_above_context_budget():
    bundle = context_bundle()
    zero_budget = bundle.model_copy(
        update={"items": (bundle.items[0].model_copy(update={"tool_budget": 0}),)}
    )
    with pytest.raises(S21ContractError) as error:
        await plan_initial_cognition(
            contexts=zero_budget,
            cognition_config=cognition_config(),
            provider_registry=provider_registry(),
            runtime=runtime(),
        )
    assert error.value.issue.code == "TOOL_REQUEST_BUDGET_EXCEEDED"
