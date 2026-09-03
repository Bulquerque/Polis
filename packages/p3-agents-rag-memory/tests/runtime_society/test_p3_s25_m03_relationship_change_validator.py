from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S25_M01_trust_relationship_updater import (
    run_module as run_m01,
)
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S25_M02_social_relationship_tool_executor import (
    run_module as run_m02,
)
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S25_M03_relationship_change_validator import (
    run_module,
)
from quant_pipeline.phase_03_agents_rag_memory.s25.errors import S25TopologyError

pytestmark = pytest.mark.unit


def upstream(valid_fixture, config_fixture):
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
    proposals = run_m02(
        {
            "updated_social_graph": updated,
            "social_tool_audit_panel": valid_fixture("social_tool_audit_panel.json"),
            "active_retro_policy_patch": valid_fixture("active_retro_policy_patch.json"),
            "relationship_formation_config": config_fixture(
                "RELATIONSHIP_FORMATION_CONFIG.yaml"
            ),
        }
    )["relationship_candidate_panel"]
    return updated, proposals


def test_applies_eligible_change_and_materializes_metrics(valid_fixture, config_fixture):
    updated, proposals = upstream(valid_fixture, config_fixture)
    result = run_module(
        {
            "updated_social_graph": updated,
            "relationship_candidate_panel": proposals,
            "social_graph_config": valid_fixture("social_graph_config_permissive.json"),
        }
    )["next_social_graph"]
    assert len(result["records"]) == 3
    assert len(result["applied_changes"]) == 1
    assert result["topology_metrics"]["connected_components"] == 1
    assert len(result["content_hash"]) == 64


def test_unreachable_minimum_topology_fails(valid_fixture, invalid_fixture, config_fixture):
    updated, proposals = upstream(valid_fixture, config_fixture)
    with pytest.raises(S25TopologyError):
        run_module(
            {
                "updated_social_graph": updated,
                "relationship_candidate_panel": proposals,
                "social_graph_config": invalid_fixture(
                    "social_graph_config_unreachable.json"
                ),
            }
        )


def test_invalid_effective_cycle_is_rejected_without_partial_edge(
    valid_fixture,
    config_fixture,
):
    updated, proposals = upstream(valid_fixture, config_fixture)
    proposals = deepcopy(proposals)
    proposals["records"][0]["effective_cycle"] = 4
    result = run_module(
        {
            "updated_social_graph": updated,
            "relationship_candidate_panel": proposals,
            "social_graph_config": valid_fixture("social_graph_config_permissive.json"),
        }
    )["next_social_graph"]
    assert len(result["records"]) == 2
    assert result["rejected_changes"][0]["reason_codes"] == ["invalid_effective_cycle"]


def test_proposal_order_does_not_change_hash(valid_fixture, config_fixture):
    updated, proposals = upstream(valid_fixture, config_fixture)
    duplicated = deepcopy(proposals["records"][0])
    duplicated["relationship_change_id"] = "relchg_second"
    duplicated["source_person_id"] = "p2"
    duplicated["target_person_id"] = "p4"
    proposals_a = deepcopy(proposals)
    proposals_a["records"].append(duplicated)
    proposals_b = deepcopy(proposals_a)
    proposals_b["records"].reverse()
    args = {
        "updated_social_graph": updated,
        "social_graph_config": valid_fixture("social_graph_config_permissive.json"),
    }
    out_a = run_module({**args, "relationship_candidate_panel": proposals_a})[
        "next_social_graph"
    ]
    out_b = run_module({**args, "relationship_candidate_panel": proposals_b})[
        "next_social_graph"
    ]
    assert out_a["content_hash"] == out_b["content_hash"]
    assert out_a == out_b
