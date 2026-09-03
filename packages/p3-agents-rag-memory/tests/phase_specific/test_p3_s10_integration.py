from __future__ import annotations

from .test_p3_s10_m01_warmup_scheduler import _inputs
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S10_M01_warmup_scheduler import run_module as schedule
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S10_M02_warmup_checkpoint_planner import run_module as plan
import json


def test_schedule_checkpoint_contract_is_consumable(root):
    scheduled = schedule(_inputs(root))["warmup_event_schedule"]
    cfg = json.loads((root / "fixtures/warmup_memory/s10/valid/warmup_checkpoint_config.json").read_text())
    checkpoints = plan({"warmup_event_schedule": scheduled, "warmup_checkpoint_config": cfg})["warmup_checkpoint_plan"]
    assert checkpoints["schedule_hash"] == scheduled["schedule_hash"]
    schedule_sequences = {item["sequence_number"] for item in scheduled["items"]}
    assert {item["after_schedule_sequence_number"] for item in checkpoints["checkpoints"]} <= schedule_sequences
