from __future__ import annotations

import copy
import json
import pytest

from quant_pipeline.phase_03_agents_rag_memory.foundation.warmup_memory.history import WarmupHistoryValidationError
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S9_M01_warmup_history_validator import run_module


def _load(root, relative):
    return json.loads((root / relative).read_text())


def test_genesis_without_history_is_explicit(root):
    output = run_module({
        "warmup_history_bundle": _load(root, "fixtures/warmup_memory/s9/valid/genesis_only.json"),
        "phase3_run_snapshot": _load(root, "fixtures/warmup_memory/s9/valid/phase3_run_snapshot.json"),
        "evaluation_window_config": _load(root, "fixtures/warmup_memory/s9/valid/evaluation_window_config.json"),
    })["validated_warmup_history"]
    assert output["mode"] == "GENESIS_ONLY"
    assert output["records"] == []


def test_history_after_cutoff_is_rejected(root):
    history = _load(root, "fixtures/warmup_memory/s9/valid/historical_replay.json")
    history["records"][0]["available_at"] = "2026-01-02T00:00:00Z"
    with pytest.raises(WarmupHistoryValidationError):
        run_module({
            "warmup_history_bundle": history,
            "phase3_run_snapshot": _load(root, "fixtures/warmup_memory/s9/valid/phase3_run_snapshot.json"),
            "evaluation_window_config": _load(root, "fixtures/warmup_memory/s9/valid/evaluation_window_config.json"),
        })
