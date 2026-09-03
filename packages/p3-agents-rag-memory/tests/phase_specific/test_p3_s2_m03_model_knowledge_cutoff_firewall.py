from __future__ import annotations

import yaml

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S2_M03_model_knowledge_cutoff_firewall import run_module

from .test_p3_s2_temporal_authority import _snapshot


def test_p3_s2_m03_allows_known_pre_as_of_model(root):
    providers, snapshot = _snapshot(root)
    result = run_module(
        {
            "phase3_run_snapshot": snapshot,
            "provider_adapter_registry_config": providers,
            "evaluation_protocol_config": yaml.safe_load(
                (root / "config/evaluation_protocol_config.yaml").read_text(encoding="utf-8")
            ),
            "model_knowledge_cutoff_policy_config": yaml.safe_load(
                (root / "config/governance/model_knowledge_cutoff_policy.yaml").read_text(encoding="utf-8")
            ),
        },
        {"execution_profile": "QUALIFICATION"},
    )
    assert result["outputs"]["model_knowledge_cutoff_report"]["overall_disposition"] == "ALLOWED_WITH_DISCLOSURE"
