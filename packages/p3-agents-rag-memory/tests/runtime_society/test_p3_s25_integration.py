from __future__ import annotations

import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S25_M01_trust_relationship_updater import (
    run_module as run_m01,
)
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S25_M02_social_relationship_tool_executor import (
    run_module as run_m02,
)
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S25_M03_relationship_change_validator import (
    run_module as run_m03,
)

pytestmark = pytest.mark.integration


def test_complete_s25_handoff(valid_fixture, config_fixture):
    updated = run_m01(
        {
            "current_social_graph": valid_fixture("current_social_graph.json"),
            "social_delivery_panel": valid_fixture("social_delivery_panel.json"),
            "validated_next_person_state_panel": valid_fixture(
                "validated_next_person_state_panel.json"
            ),
            "active_belief_feedback_bundle": valid_fixture(
                "active_belief_feedback_bundle.json"
            ),
            "relationship_update_config": config_fixture("RELATIONSHIP_UPDATE_CONFIG.yaml"),
        }
    )["updated_social_graph"]
    candidates = run_m02(
        {
            "updated_social_graph": updated,
            "social_tool_audit_panel": valid_fixture("social_tool_audit_panel.json"),
            "active_retro_policy_patch": valid_fixture("active_retro_policy_patch.json"),
            "relationship_formation_config": config_fixture(
                "RELATIONSHIP_FORMATION_CONFIG.yaml"
            ),
        }
    )["relationship_candidate_panel"]
    next_graph = run_m03(
        {
            "updated_social_graph": updated,
            "relationship_candidate_panel": candidates,
            "social_graph_config": valid_fixture("social_graph_config_permissive.json"),
        }
    )["next_social_graph"]

    assert updated["run_id"] == candidates["run_id"] == next_graph["run_id"]
    assert updated["cycle_id"] == candidates["cycle_id"] == next_graph["cycle_id"]
    assert any(record["valid_from_cycle"] <= 4 for record in next_graph["records"])
    assert any(record["valid_from_cycle"] == 5 for record in next_graph["records"])
    assert next_graph["lineage_id"] not in {
        updated["lineage_id"],
        candidates["lineage_id"],
    }
