from __future__ import annotations

import pytest

from quant_pipeline.phase_03_agents_rag_memory.contracts import (
    ExecutionProfile,
    ModuleExecutionContext,
)
from quant_pipeline.phase_03_agents_rag_memory.s20.errors import S20ContractError
from quant_pipeline.phase_03_agents_rag_memory.modules import (
    P3_S20_M02_hybrid_memory_rag_retriever as m02,
    P3_S20_M03_graph_rag_query_executor as m03,
    P3_S20_M05_retrieval_reranker_evidence_bundle_builder as m05,
    P3_S20_M06_person_context_assembler as m06,
    P3_S20_M07_context_budget_validator as m07,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "service_name"),
    [
        (m02, "memory_port"),
        (m03, "graph_query_port"),
        (m05, "reranker_port"),
        (m06, "tokenizer_port"),
        (m07, "tokenizer_port"),
    ],
)
async def test_live_profile_refuses_implicit_reference_services(module, service_name):
    context = ModuleExecutionContext(profile=ExecutionProfile.LIVE)
    with pytest.raises(S20ContractError, match=service_name):
        await module.execute({}, context)


@pytest.mark.asyncio
async def test_replay_profile_refuses_live_retrieval_without_frozen_ports():
    context = ModuleExecutionContext(profile=ExecutionProfile.REPLAY)
    with pytest.raises(S20ContractError, match="memory_port"):
        await m02.execute({}, context)
