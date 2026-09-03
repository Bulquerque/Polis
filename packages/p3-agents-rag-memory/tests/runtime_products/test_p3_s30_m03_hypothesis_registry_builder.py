from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M01_social_feature_builder import run_module as m1
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M02_context_memory_feature_builder import run_module as m2
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M03_hypothesis_registry_builder import (
    IMPLEMENTED,
    MODULE_ID,
    run_module,
)
from quant_pipeline.phase_03_agents_rag_memory.s30_products import S30ContractError


def _upstream_products(s30_upstream_inputs, s30_execution_context, s30_projection_config):
    cfg = {"execution_context": s30_execution_context, "feature_projection_config": s30_projection_config}
    social = m1(
        {k: s30_upstream_inputs[k] for k in (
            "validated_society_state_panel", "evidence_tag_panel", "agent_disagreement_panel"
        )}, cfg
    )["outputs"]["social_feature_panel"]
    memory = m2(
        {k: s30_upstream_inputs[k] for k in (
            "next_memory_state", "validated_society_state_panel", "evidence_tag_panel"
        )}, cfg
    )["outputs"]["context_memory_feature_panel"]
    return social, memory


def test_module_identity_and_implementation():
    assert MODULE_ID == "P3.S30.M03"
    assert IMPLEMENTED is True


def test_builds_specific_falsifiable_hypothesis(
    s30_upstream_inputs, s30_execution_context, s30_projection_config, s30_proposition_config
):
    social, memory = _upstream_products(s30_upstream_inputs, s30_execution_context, s30_projection_config)
    output = run_module({
        "social_feature_panel": social,
        "context_memory_feature_panel": memory,
        "evidence_tag_panel": s30_upstream_inputs["evidence_tag_panel"],
        "agent_disagreement_panel": s30_upstream_inputs["agent_disagreement_panel"],
        "proposition_registry_config": s30_proposition_config,
    }, {"execution_context": s30_execution_context})["outputs"]["hypothesis_registry"]
    assert len(output["records"]) == 1
    row = output["records"][0]
    assert row["underlying_id"] == "PETR4"
    assert row["horizon"] == "21d"
    assert row["falsification_criterion"]
    assert row["supporting_evidence_refs"] == ["evidence-001"]
    assert row["opposing_evidence_refs"] == ["evidence-002"]


def test_generic_template_without_required_tokens_fails(
    s30_upstream_inputs, s30_execution_context, s30_projection_config, s30_proposition_config
):
    social, memory = _upstream_products(s30_upstream_inputs, s30_execution_context, s30_projection_config)
    broken = deepcopy(s30_proposition_config)
    broken["propositions"][0]["statement_template"] = "Generic hypothesis"
    with pytest.raises(S30ContractError, match="statement_template"):
        run_module({
            "social_feature_panel": social,
            "context_memory_feature_panel": memory,
            "evidence_tag_panel": s30_upstream_inputs["evidence_tag_panel"],
            "agent_disagreement_panel": s30_upstream_inputs["agent_disagreement_panel"],
            "proposition_registry_config": broken,
        }, {"execution_context": s30_execution_context})


def test_insufficient_evidence_returns_blocked_empty_registry(
    s30_upstream_inputs, s30_execution_context, s30_projection_config, s30_proposition_config
):
    social, memory = _upstream_products(s30_upstream_inputs, s30_execution_context, s30_projection_config)
    changed = deepcopy(s30_proposition_config)
    changed["propositions"][0]["minimum_evidence_count"] = 99
    output = run_module({
        "social_feature_panel": social,
        "context_memory_feature_panel": memory,
        "evidence_tag_panel": s30_upstream_inputs["evidence_tag_panel"],
        "agent_disagreement_panel": s30_upstream_inputs["agent_disagreement_panel"],
        "proposition_registry_config": changed,
    }, {"execution_context": s30_execution_context})["outputs"]["hypothesis_registry"]
    assert output["records"] == []
    assert output["quality_status"] == "BLOCKED"
