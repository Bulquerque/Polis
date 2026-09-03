from __future__ import annotations

import copy
import pytest
import yaml

from quant_pipeline.phase_03_agents_rag_memory.foundation.learning_feedback.errors import S3ContractError
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S3_M01_promoted_retro_update_ingestor import run_module


def _inputs(root, governance_outputs):
    snapshot = copy.deepcopy(governance_outputs["phase3_run_snapshot"])
    lineage = "lineage-p9-retro-empty"
    return {
        "retro_memory_update_package": {
            "artifact_id": "retro-empty",
            "lineage_id": lineage,
            "created_at": "2026-07-26T00:00:00Z",
            "patches": [],
        },
        "phase3_retro_handoff_manifest": {
            "artifact_id": "retro-manifest-empty",
            "lineage_id": lineage,
            "created_at": "2026-07-26T00:00:00Z",
            "pipeline_version": "V14.1-RC4.1",
        },
        "phase3_run_snapshot": snapshot,
        "retro_patch_compatibility_config": yaml.safe_load(
            (root / "config/governance/RETRO_PATCH_COMPATIBILITY_CONFIG.yaml").read_text()
        ),
    }


def test_no_patch_is_explicit(root, governance_outputs):
    output = run_module(_inputs(root, governance_outputs), {"current_cycle_id": 2, "processed_at": "2026-07-27T12:00:00Z", "package_root": root})
    patch = output["outputs"]["active_retro_policy_patch"]
    assert patch["status"] == "NO_PATCH"
    assert patch["patch"] is None


def test_future_patch_handoff_is_rejected(root, governance_outputs):
    inputs = _inputs(root, governance_outputs)
    inputs["retro_memory_update_package"]["created_at"] = "2026-07-28T00:00:00Z"
    with pytest.raises(S3ContractError, match="TEMPORAL_VIOLATION"):
        run_module(inputs, {"current_cycle_id": 2, "processed_at": "2026-07-27T12:00:00Z", "package_root": root})
