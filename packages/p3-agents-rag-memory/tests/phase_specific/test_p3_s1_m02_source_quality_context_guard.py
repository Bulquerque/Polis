from __future__ import annotations

import yaml

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S1_M01_phase2_handoff_contract_validator import run_module as run_m01
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S1_M02_source_quality_context_guard import run_module

from .test_p3_s2_temporal_authority import _s1


def test_p3_s1_m02_preserves_accepted_context_without_rejection(root):
    payload, _ = _s1(root)
    handoff = run_m01(payload)["outputs"]["validated_phase2_handoff"]
    result = run_module(
        {
            "validated_phase2_handoff": handoff,
            "source_quality_panel": payload["source_quality_panel"],
            "source_quality_policy_config": yaml.safe_load(
                (root / "config/governance/SOURCE_QUALITY_POLICY.yaml").read_text(encoding="utf-8")
            ),
        }
    )
    assert result["outputs"]["validated_context_inputs"]["summary"]["rejected"] == 0
