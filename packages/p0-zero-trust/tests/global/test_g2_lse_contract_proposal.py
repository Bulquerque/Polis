from pathlib import Path

import yaml


def workspace_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "GLOBAL_MODULE_TABLE.csv").exists():
            return candidate
    raise AssertionError("workspace root not found")


def test_g2_lse_proposal_is_explicitly_gated_and_connected_only_to_p1():
    root = workspace_root()
    proposal = yaml.safe_load((root / "reports/planning/data_api_agent_modernization/g2_p1_lse_contract_proposal.yaml").read_text(encoding="utf-8"))
    schema = yaml.safe_load((root / "reports/planning/data_api_agent_modernization/g2_p1_lse_schema_proposal.yaml").read_text(encoding="utf-8"))

    assert proposal["status"] == "proposal_only"
    assert proposal["module_id"] == "P1.S2.M08"
    assert proposal["outputs"] == ["london_strategic_edge_raw_capture_inventory"]
    assert proposal["allowed_connections"]["emits_to"]["modules"] == ["P1.S3.M01"]
    assert proposal["runtime_activation_gate"] == "G0_clean_and_G2_approval"
    assert schema["artifact"] == proposal["outputs"][0]
    assert "content_hash" in schema["required_fields"]
    assert "credentials_are_not_emitted" in proposal["validations"]
    assert "trade_decision" in schema["forbidden_fields"]
