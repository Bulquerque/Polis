from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M02_context_memory_feature_builder import (
    IMPLEMENTED,
    MODULE_ID,
    REQUIRED_INPUTS,
    run_module,
)
from quant_pipeline.phase_03_agents_rag_memory.s30_products import S30PrivacyError


def _run(s30_upstream_inputs, s30_execution_context, s30_projection_config):
    return run_module(
        {name: s30_upstream_inputs[name] for name in REQUIRED_INPUTS},
        {
            "execution_context": s30_execution_context,
            "feature_projection_config": s30_projection_config,
        },
    )["outputs"]["context_memory_feature_panel"]


def test_module_identity_and_implementation():
    assert MODULE_ID == "P3.S30.M02"
    assert IMPLEMENTED is True


def test_projects_aggregate_only_memory_and_context(
    s30_upstream_inputs, s30_execution_context, s30_projection_config
):
    output = _run(s30_upstream_inputs, s30_execution_context, s30_projection_config)
    assert len(output["records"]) == 9
    by_id = {row["context_memory_feature_id"]: row for row in output["records"]}
    assert by_id["memory.item_count"]["feature_value"] == 2.0
    assert by_id["memory.population_coverage_ratio"]["feature_value"] == 0.5
    assert by_id["context.evidence_count"]["feature_value"] == 2.0
    assert all(row["privacy_class"] == "INTERNAL_AGGREGATE" for row in output["records"])


def test_empty_memory_is_material_not_failure(
    s30_upstream_inputs, s30_execution_context, s30_projection_config
):
    changed = deepcopy(s30_upstream_inputs)
    changed["next_memory_state"]["records"] = []
    output = _run(changed, s30_execution_context, s30_projection_config)
    by_id = {row["context_memory_feature_id"]: row for row in output["records"]}
    assert by_id["memory.item_count"]["feature_value"] == 0.0
    assert by_id["memory.population_coverage_ratio"]["feature_value"] == 0.0
    assert output["quality_status"] == "DEGRADED"


def test_private_content_field_is_rejected(
    s30_upstream_inputs, s30_execution_context, s30_projection_config
):
    broken = deepcopy(s30_upstream_inputs)
    broken["next_memory_state"]["records"][0]["content"] = "private memory text"
    with pytest.raises(S30PrivacyError, match="private field"):
        _run(broken, s30_execution_context, s30_projection_config)
