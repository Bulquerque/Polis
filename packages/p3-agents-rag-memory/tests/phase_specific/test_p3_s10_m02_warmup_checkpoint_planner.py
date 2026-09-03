from __future__ import annotations

import json
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S10_M01_warmup_scheduler import run_module as schedule
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S10_M02_warmup_checkpoint_planner import run_module


def _load(root, relative):
    return json.loads((root / relative).read_text())


def test_checkpoint_plan_references_schedule(root):
    event_schedule = schedule({
        "validated_warmup_history": _load(root, "fixtures/warmup_memory/s10/valid/validated_warmup_history.json"),
        "validated_population_manifest": _load(root, "fixtures/warmup_memory/s10/valid/validated_population_manifest.json"),
        "validated_initial_social_graph": _load(root, "fixtures/warmup_memory/s10/valid/validated_initial_social_graph.json"),
        "activation_config": _load(root, "fixtures/warmup_memory/s10/valid/activation_config.json"),
        "heartbeat_config": _load(root, "fixtures/warmup_memory/s10/valid/heartbeat_config.json"),
    })["warmup_event_schedule"]
    output = run_module({
        "warmup_event_schedule": event_schedule,
        "warmup_checkpoint_config": _load(root, "fixtures/warmup_memory/s10/valid/warmup_checkpoint_config.json"),
    })["warmup_checkpoint_plan"]
    assert output["schedule_hash"] == event_schedule["schedule_hash"]
    assert output["checkpoints"]
