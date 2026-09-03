from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M01_social_feature_builder import run_module as m1
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M02_context_memory_feature_builder import run_module as m2
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M03_hypothesis_registry_builder import run_module as m3
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M04_phase4_social_handoff_builder import run_module as m4
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M05_variable_evolution_handoff_builder import run_module as m5
from quant_pipeline.phase_03_agents_rag_memory.s30_products import (
    S30ContractError,
    S30IntegrityError,
    S30TemporalError,
)


@pytest.mark.parametrize("runner", [m1, m2, m3, m4, m5])
def test_every_wrapper_requires_explicit_execution_context(runner):
    with pytest.raises(ValueError, match="execution context"):
        runner({}, {})


def test_projection_wrappers_require_catalog(s30_execution_context):
    with pytest.raises(ValueError, match="feature_projection_config"):
        m1({}, {"execution_context": s30_execution_context})
    with pytest.raises(ValueError, match="feature_projection_config"):
        m2({}, {"execution_context": s30_execution_context})


def test_m04_rejects_non_mapping_expected_hashes(s30_execution_context):
    with pytest.raises(ValueError, match="expected_artifact_hashes"):
        m4({}, {"execution_context": s30_execution_context, "expected_artifact_hashes": []})


@pytest.mark.parametrize(
    ("runner", "inputs", "config", "module_id"),
    [
        (m1, {}, "projection", "M01"),
        (m2, {}, "projection", "M02"),
        (m3, {}, "proposition", "M03"),
        (m4, {}, None, "M04"),
        (m5, {}, None, "M05"),
    ],
)
def test_each_module_fails_closed_on_missing_inputs(
    runner,
    inputs,
    config,
    module_id,
    s30_execution_context,
    s30_projection_config,
    s30_proposition_config,
):
    cfg = {"execution_context": s30_execution_context}
    if config == "projection":
        cfg["feature_projection_config"] = s30_projection_config
    payload = dict(inputs)
    if config == "proposition":
        payload["proposition_registry_config"] = s30_proposition_config
    with pytest.raises(S30ContractError, match=module_id):
        runner(payload, cfg)


def test_m01_rejects_duplicate_society_grain(
    s30_upstream_inputs, s30_execution_context, s30_projection_config
):
    broken = deepcopy(s30_upstream_inputs)
    broken["validated_society_state_panel"]["records"].append(
        deepcopy(broken["validated_society_state_panel"]["records"][0])
    )
    with pytest.raises(S30ContractError, match="duplicate society state"):
        m1(
            {
                "validated_society_state_panel": broken["validated_society_state_panel"],
                "evidence_tag_panel": broken["evidence_tag_panel"],
                "agent_disagreement_panel": broken["agent_disagreement_panel"],
            },
            {
                "execution_context": s30_execution_context,
                "feature_projection_config": s30_projection_config,
            },
        )


def test_m01_rejects_created_at_before_as_of(
    s30_upstream_inputs, s30_execution_context, s30_projection_config
):
    broken = deepcopy(s30_upstream_inputs)
    broken["validated_society_state_panel"]["created_at"] = "2024-01-31T19:59:59Z"
    with pytest.raises(S30ContractError, match="created_at"):
        m1(
            {
                "validated_society_state_panel": broken["validated_society_state_panel"],
                "evidence_tag_panel": broken["evidence_tag_panel"],
                "agent_disagreement_panel": broken["agent_disagreement_panel"],
            },
            {
                "execution_context": s30_execution_context,
                "feature_projection_config": s30_projection_config,
            },
        )


def test_m01_rejects_context_as_of_mismatch(
    s30_upstream_inputs, s30_execution_context, s30_projection_config
):
    context = deepcopy(s30_execution_context)
    context["as_of_time"] = "2024-01-31T19:00:00Z"
    with pytest.raises(S30TemporalError, match="as_of_time"):
        m1(
            {
                "validated_society_state_panel": s30_upstream_inputs["validated_society_state_panel"],
                "evidence_tag_panel": s30_upstream_inputs["evidence_tag_panel"],
                "agent_disagreement_panel": s30_upstream_inputs["agent_disagreement_panel"],
            },
            {"execution_context": context, "feature_projection_config": s30_projection_config},
        )


def test_m04_rejects_unknown_expected_hash_key(
    s30_products, s30_upstream_inputs, s30_execution_context
):
    with pytest.raises(S30IntegrityError, match="unknown artifacts"):
        m4(
            {
                "social_feature_panel": s30_products["social_feature_panel"],
                "evidence_tag_panel": s30_upstream_inputs["evidence_tag_panel"],
                "agent_disagreement_panel": s30_upstream_inputs["agent_disagreement_panel"],
                "context_memory_feature_panel": s30_products["context_memory_feature_panel"],
                "hypothesis_registry": s30_products["hypothesis_registry"],
                "phase3_run_snapshot": s30_upstream_inputs["phase3_run_snapshot"],
            },
            {
                "execution_context": s30_execution_context,
                "expected_artifact_hashes": {"unknown_artifact": "0" * 64},
            },
        )


def test_m05_rejects_snapshot_pipeline_version_mismatch(
    s30_products, s30_upstream_inputs, s30_execution_context
):
    broken = deepcopy(s30_upstream_inputs)
    broken["phase3_run_snapshot"]["pipeline_version"] = "V14.1-INCOMPATIBLE"
    with pytest.raises(S30ContractError, match="phase3_run_snapshot"):
        m5(
            {
                "validated_society_state_panel": broken["validated_society_state_panel"],
                "social_feature_panel": s30_products["social_feature_panel"],
                "context_memory_feature_panel": s30_products["context_memory_feature_panel"],
                "hypothesis_registry": s30_products["hypothesis_registry"],
                "belief_outcome_commitment_log": broken["belief_outcome_commitment_log"],
                "phase3_run_snapshot": broken["phase3_run_snapshot"],
            },
            {"execution_context": s30_execution_context},
        )
