from __future__ import annotations

import asyncio

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.modules import (
    P3_S33_M01_phase2_research_view_manifest_builder as m01,
    P3_S33_M02_phase1_raw_evidence_reference_index_builder as m02,
    P3_S33_M03_temporal_visibility_vintage_firewall_builder as m03,
    P3_S33_M04_temporal_entity_instrument_resolver_builder as m04,
    P3_S33_M05_research_data_boundary_bundle_builder as m05,
)

from .support_s33 import DECISION_TIME, load_yaml, p1_inputs, p2_inputs, s32_outputs


def test_s33_wrappers_execute_end_to_end():
    context = ModuleExecutionContext()
    s32 = s32_outputs()
    p2 = p2_inputs()
    out1 = asyncio.run(m01.execute({**s32, **p2}, context))
    out2 = asyncio.run(m02.execute({**p1_inputs(), **p2, **out1}, context))
    out3 = asyncio.run(m03.execute({
        **s32, **out1, **out2,
        "phase3_run_snapshot": {"snapshot_id": "p3", "decision_time": DECISION_TIME, "execution_mode": "BACKTEST"},
        "evaluation_window_config": {"decision_time": DECISION_TIME},
        "pit_data_view_policy_config": load_yaml("config/research_tools/PIT_DATA_VIEW_POLICY.yaml"),
        "calendar_timezone_policy_config": load_yaml("config/research_tools/CALENDAR_TIMEZONE_POLICY.yaml"),
        "vintage_policy_config": load_yaml("config/research_tools/VINTAGE_POLICY_REGISTRY.yaml"),
    }, context))
    out4 = asyncio.run(m04.execute({
        **p2, **out1, **out3,
        "entity_underlying_map_config": load_yaml("config/research_tools/ENTITY_UNDERLYING_MAP.yaml"),
    }, context))
    out5 = asyncio.run(m05.execute({**s32, **out1, **out2, **out3, **out4}, context))
    assert out5["research_data_boundary_bundle"]["status"] == "READY"
    assert out5["research_boundary_preflight_report"]["overall_status"] == "PASS"


def test_s33_does_not_mutate_s32_snapshot():
    before = s32_outputs()["research_tool_extension_snapshot"]["content_hash"]
    test_s33_wrappers_execute_end_to_end()
    after = s32_outputs()["research_tool_extension_snapshot"]["content_hash"]
    assert before == after
