from pathlib import Path

import yaml


def workspace_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "GLOBAL_MODULE_TABLE.csv").exists():
            return candidate
    raise AssertionError("workspace root not found")


def proposal(root: Path, name: str) -> dict:
    path = root / "reports/planning/data_api_agent_modernization" / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_g3_p2_proposal_enforces_bitemporal_fields_and_gate():
    item = proposal(workspace_root(), "g3_p2_bitemporal_contract_proposal.yaml")
    assert item["status"] == "proposal_only"
    assert item["phase"] == "phase_02_quality_pit"
    assert set(item["required_temporal_fields"]) >= {"valid_from", "available_at", "retrieved_at"}
    assert "available_at_must_be_at_or_before_as_of_date" in item["validations"]
    assert item["proposed_new_output"]["approval_required"] is True


def test_g4_p3_proposal_forbids_direct_raw_access_and_limits_mcp():
    item = proposal(workspace_root(), "g4_p3_agent_stack_contract_proposal.yaml")
    assert item["status"] == "proposal_only"
    assert item["orchestration"]["framework"] == "LangGraph"
    assert item["llm"]["agent_selects_model"] is False
    market = next(server for server in item["mcp_servers"] if server["server_id"] == "market_data_mcp")
    assert market["scope"] == "phase3_market_context_panel_only"
    assert "direct_external_raw_access_forbidden" in item["required_rules"]


def test_g5_p9_proposal_enforces_next_cycle_and_existing_retro_handoff():
    item = proposal(workspace_root(), "g5_p9_next_cycle_contract_proposal.yaml")
    assert item["status"] == "proposal_only"
    assert "target_cycle_must_be_greater_than_source_cycle" in item["required_rules"]
    assert "current_backtest_is_immutable" in item["required_rules"]
    assert set(item["allowed_phase3_handoff"]["artifacts"]) == {
        "retro_memory_update_package",
        "phase3_retro_handoff_manifest",
    }
