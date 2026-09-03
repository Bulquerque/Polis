from __future__ import annotations
import json
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S9_M01_warmup_history_validator import run_module as history
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S10_M01_warmup_scheduler import run_module as schedule


def _load(root, relative):
    return json.loads((root/relative).read_text())


def test_genesis_history_flows_into_genesis_schedule(root):
    validated=history({
        "warmup_history_bundle":_load(root,"fixtures/warmup_memory/s9/valid/genesis_only.json"),
        "phase3_run_snapshot":_load(root,"fixtures/warmup_memory/s9/valid/phase3_run_snapshot.json"),
        "evaluation_window_config":_load(root,"fixtures/warmup_memory/s9/valid/evaluation_window_config.json"),
    })["validated_warmup_history"]
    out=schedule({
        "validated_warmup_history":validated,
        "validated_population_manifest":_load(root,"fixtures/warmup_memory/s10/valid/validated_population_manifest.json"),
        "validated_initial_social_graph":_load(root,"fixtures/warmup_memory/s10/valid/validated_initial_social_graph.json"),
        "activation_config":_load(root,"fixtures/warmup_memory/s10/valid/activation_config.json"),
        "heartbeat_config":_load(root,"fixtures/warmup_memory/s10/valid/heartbeat_config.json"),
    })["warmup_event_schedule"]
    assert validated["mode"]=="GENESIS_ONLY"
    assert out["mode"]=="GENESIS_ONLY"
