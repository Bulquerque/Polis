from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M01_social_feature_builder import (
    IMPLEMENTED,
    MODULE_ID,
    REQUIRED_INPUTS,
    run_module,
)
from quant_pipeline.phase_03_agents_rag_memory.s30_products import S30ContractError


def _run(s30_upstream_inputs, s30_execution_context, s30_projection_config):
    return run_module(
        {name: s30_upstream_inputs[name] for name in REQUIRED_INPUTS},
        {
            "execution_context": s30_execution_context,
            "feature_projection_config": s30_projection_config,
        },
    )["outputs"]["social_feature_panel"]


def test_module_identity_and_implementation():
    assert MODULE_ID == "P3.S30.M01"
    assert IMPLEMENTED is True
    assert REQUIRED_INPUTS == (
        "validated_society_state_panel",
        "evidence_tag_panel",
        "agent_disagreement_panel",
    )


def test_builds_allowlisted_legacy_compatible_features(
    s30_upstream_inputs, s30_execution_context, s30_projection_config
):
    output = _run(s30_upstream_inputs, s30_execution_context, s30_projection_config)
    assert len(output["records"]) == 12
    required = {
        "date", "as_of_date", "available_at", "underlying", "social_feature_id",
        "feature_name", "feature_value", "feature_type", "source_quality_score",
        "evidence_count", "agent_agreement_score", "agent_disagreement_score",
        "reference_date", "lineage_id", "pipeline_version",
    }
    assert all(required <= set(row) for row in output["records"])
    assert {row["underlying"] for row in output["records"]} == {"PETR4"}
    assert all(row["date"] == "2024-01-31" for row in output["records"])


def test_output_is_deterministic_under_input_permutation(
    s30_upstream_inputs, s30_execution_context, s30_projection_config
):
    first = _run(s30_upstream_inputs, s30_execution_context, s30_projection_config)
    changed = deepcopy(s30_upstream_inputs)
    changed["evidence_tag_panel"]["records"].reverse()
    second = _run(changed, s30_execution_context, s30_projection_config)
    assert first == second


def test_rejects_grain_mismatch(s30_upstream_inputs, s30_execution_context, s30_projection_config):
    broken = deepcopy(s30_upstream_inputs)
    broken["agent_disagreement_panel"]["records"][0]["horizon"] = "63d"
    with pytest.raises(S30ContractError, match="grain mismatch"):
        _run(broken, s30_execution_context, s30_projection_config)


def test_rejects_forbidden_field(s30_upstream_inputs, s30_execution_context, s30_projection_config):
    broken = deepcopy(s30_upstream_inputs)
    broken["validated_society_state_panel"]["future_return"] = 0.1
    with pytest.raises(S30ContractError, match="forbidden field"):
        _run(broken, s30_execution_context, s30_projection_config)
