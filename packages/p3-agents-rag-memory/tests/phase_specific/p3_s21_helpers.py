from __future__ import annotations

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S21_M01_initial_llm_cognition_planner import run_module_async as run_m01
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S21_M02_tool_call_request_validator import run_module as run_m02
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S21_M03_mcp_tool_executor import run_module_async as run_m03
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S21_M04_tool_result_validator import run_module as run_m04
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S21_M05_llm_cognition_continuation_runner import run_module_async as run_m05
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S21_M06_structured_belief_proposal_parser import run_module as run_m06
from .p3_s21_factories import *


async def run_through_m01(rt=None):
    rt = rt or runtime()
    out = await run_m01(
        {
            "validated_person_context_bundle": context_bundle().model_dump(mode="json"),
            "cognition_config": cognition_config().model_dump(mode="json"),
            "provider_adapter_registry_config": provider_registry().model_dump(mode="json"),
        },
        runtime=rt,
    )
    return rt, out


async def run_through_m02(rt=None):
    rt, out = await run_through_m01(rt)
    out2 = run_m02(
        {
            "tool_call_request_panel": out["tool_call_request_panel"],
            "person_tool_entitlement_panel": entitlement_panel().model_dump(mode="json"),
            "mcp_gateway_policy": gateway_policy().model_dump(mode="json"),
            "tool_call_audit_contract": audit_contract().model_dump(mode="json"),
        }
    )
    return rt, out, out2


async def run_through_m03(rt=None):
    rt, out, out2 = await run_through_m02(rt)
    out3 = await run_m03(
        {
            "validated_tool_call_request_panel": out2["validated_tool_call_request_panel"],
            "mcp_gateway_policy": gateway_policy().model_dump(mode="json"),
            "tool_call_audit_contract": audit_contract().model_dump(mode="json"),
            "provider_adapter_registry_config": provider_registry().model_dump(mode="json"),
        },
        runtime=rt,
    )
    return rt, out, out2, out3


async def run_through_m04(rt=None):
    rt, out, out2, out3 = await run_through_m03(rt)
    out4 = run_m04(
        {
            "raw_tool_result_panel": out3["raw_tool_result_panel"],
            "tool_call_audit_panel": out3["tool_call_audit_panel"],
            "phase3_run_snapshot": snapshot().model_dump(mode="json"),
            "retrieval_evidence_map": evidence_map().model_dump(mode="json"),
        }
    )
    return rt, out, out2, out3, out4


async def run_through_m05(rt=None):
    rt, out, out2, out3, out4 = await run_through_m04(rt)
    out5 = await run_m05(
        {
            "initial_agent_reading_panel": out["initial_agent_reading_panel"],
            "preliminary_belief_proposal_panel": out["preliminary_belief_proposal_panel"],
            "validated_tool_result_panel": out4["validated_tool_result_panel"],
            "validated_person_context_bundle": context_bundle().model_dump(mode="json"),
            "cognition_config": cognition_config().model_dump(mode="json"),
            "provider_adapter_registry_config": provider_registry().model_dump(mode="json"),
            "social_intent_panel": out["social_intent_panel"],
            "attention_followup_intent_panel": out["attention_followup_intent_panel"],
        },
        runtime=rt,
    )
    return rt, out, out2, out3, out4, out5


async def run_through_m06(rt=None):
    rt, out, out2, out3, out4, out5 = await run_through_m05(rt)
    out6 = run_m06(
        {
            "raw_belief_proposal_panel": out5["raw_belief_proposal_panel"],
            "proposition_registry_config": proposition_registry().model_dump(mode="json"),
        }
    )
    return rt, out, out2, out3, out4, out5, out6
