from __future__ import annotations

import json
from pathlib import Path

import yaml


def load_inputs(plan_root: Path) -> tuple[dict, dict]:
    fixture_root = plan_root / "fixtures" / "capabilities" / "context" / "s19"
    inputs = {
        "stimulus_panel": json.loads((fixture_root / "stimulus_panel.valid.json").read_text()),
        "current_person_state_panel": json.loads(
            (fixture_root / "current_person_state_panel.valid.json").read_text()
        ),
        "person_seed_panel": json.loads(
            (fixture_root / "person_seed_panel.valid.json").read_text()
        ),
        "validated_population_manifest": json.loads(
            (fixture_root / "validated_population_manifest.valid.json").read_text()
        ),
    }
    config = {
        "activation_config": yaml.safe_load(
            (plan_root / "src/quant_pipeline/phase_03_agents_rag_memory/runtime_engine/assets/config/context/s19/ACTIVATION_S19_CONFIG.yaml").read_text()
        ),
        "heartbeat_config": yaml.safe_load(
            (plan_root / "src/quant_pipeline/phase_03_agents_rag_memory/runtime_engine/assets/config/context/s19/HEARTBEAT_S19_CONFIG.yaml").read_text()
        ),
    }
    return inputs, config
