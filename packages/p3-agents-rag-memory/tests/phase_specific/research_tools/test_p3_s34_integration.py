from __future__ import annotations

import asyncio
from importlib import import_module

from .support_s34 import (
    build_s34_m01, build_s34_m02, build_s34_m03, build_s34_m04, build_s34_m05,
    person_inputs, person_schema_policy, run_snapshot, legacy_entitlements, gateway_policy,
    s20_context_bundle, cognition_config,
)
from .support import load_yaml
from .support_s33 import build_s33_m01, s32_outputs
from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext


def test_end_to_end_s32_s33_s34_chain() -> None:
    outputs = {**s32_outputs(), **build_s33_m01(), **build_s34_m01(), **build_s34_m02(), **build_s34_m03(), **build_s34_m04(), **build_s34_m05()}
    assert outputs["research_capability_taxonomy"]["status"] == "READY"
    assert outputs["capability_profile_coverage_report"]["coverage_ratio"] == 1.0
    assert outputs["extended_person_tool_entitlement_panel"]["records"]
    assert outputs["extended_validated_person_context_bundle"]["items"]


def test_all_five_wrappers_execute_against_declared_contracts() -> None:
    base = {**s32_outputs(), **build_s33_m01(), **person_inputs(), "person_schema_policy": person_schema_policy(), "phase3_run_snapshot": run_snapshot()}
    ctx = ModuleExecutionContext(cycle_id="cycle-s34")
    specs = [
        ("P3_S34_M01_research_capability_taxonomy_builder", {**base, "research_capability_taxonomy_config": load_yaml("config/research_tools/RESEARCH_CAPABILITY_TAXONOMY.yaml")}),
        ("P3_S34_M02_person_research_capability_profiler", {**base, **build_s34_m01(), "capability_profile_policy_config": load_yaml("config/research_tools/CAPABILITY_PROFILE_POLICY.yaml")}),
        ("P3_S34_M03_research_plan_template_registry_builder", {**base, **build_s34_m01(), "research_plan_registry_config": load_yaml("config/research_tools/RESEARCH_PLAN_REGISTRY.yaml")}),
        ("P3_S34_M04_effective_entitlement_overlay_builder", {**base, **build_s34_m02(), **build_s34_m03(), "person_tool_entitlement_panel": legacy_entitlements(), "research_entitlement_policy_config": load_yaml("config/research_tools/RESEARCH_ENTITLEMENT_POLICY.yaml"), "mcp_gateway_policy": gateway_policy()}),
        ("P3_S34_M05_person_context_tool_descriptor_overlay_builder", {**base, **build_s34_m01(), **build_s34_m02(), **build_s34_m03(), **build_s34_m04(), "validated_person_context_bundle": s20_context_bundle(), "cognition_config": cognition_config(), "context_tool_descriptor_policy_config": load_yaml("config/research_tools/CONTEXT_TOOL_DESCRIPTOR_POLICY.yaml")}),
    ]
    for module_name, inputs in specs:
        module = import_module(f"quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.modules.{module_name}")
        result = asyncio.run(module.execute(inputs, ctx))
        assert set(result) == set(module.PRODUCED_OUTPUTS)
