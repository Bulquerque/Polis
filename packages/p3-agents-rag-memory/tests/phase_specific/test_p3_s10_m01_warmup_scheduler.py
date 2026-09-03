from __future__ import annotations

import json
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S10_M01_warmup_scheduler import run_module


def _load(root, relative):
    return json.loads((root / relative).read_text())


def _inputs(root, genesis=False):
    suffix = "validated_warmup_history_genesis.json" if genesis else "validated_warmup_history.json"
    return {
        "validated_warmup_history": _load(root, f"fixtures/warmup_memory/s10/valid/{suffix}"),
        "validated_population_manifest": _load(root, "fixtures/warmup_memory/s10/valid/validated_population_manifest.json"),
        "validated_initial_social_graph": _load(root, "fixtures/warmup_memory/s10/valid/validated_initial_social_graph.json"),
        "activation_config": _load(root, "fixtures/warmup_memory/s10/valid/activation_config.json"),
        "heartbeat_config": _load(root, "fixtures/warmup_memory/s10/valid/heartbeat_config.json"),
    }


def test_schedule_is_stably_ordered(root):
    first = run_module(_inputs(root))["warmup_event_schedule"]
    second = run_module(_inputs(root))["warmup_event_schedule"]
    assert first["schedule_hash"] == second["schedule_hash"]
    times = [item["logical_time"] for item in first["items"]]
    assert times == sorted(times)


def test_genesis_schedule_is_valid(root):
    output = run_module(_inputs(root, genesis=True))["warmup_event_schedule"]
    assert output["mode"] == "GENESIS_ONLY"
