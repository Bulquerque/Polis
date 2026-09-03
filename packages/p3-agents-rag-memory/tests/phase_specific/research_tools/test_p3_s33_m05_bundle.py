from __future__ import annotations

from .support_s33 import build_s33_m01, build_s33_m02, build_s33_m03, build_s33_m04, build_s33_m05


def test_m05_builds_four_read_only_offline_ports():
    out = build_s33_m05()
    bundle = out["research_data_boundary_bundle"]
    assert len(bundle["ports"]) == 4
    assert all(item["read_only"] is True for item in bundle["ports"])
    assert all(item["network_required"] is False for item in bundle["ports"])
    assert out["research_boundary_preflight_report"]["overall_status"] == "PASS"


def test_m05_contains_refs_not_embedded_upstream_payloads():
    bundle = build_s33_m05()["research_data_boundary_bundle"]
    text = str(bundle)
    assert "clean_underlying_panel-0" not in text
    assert "raw/sec/snapshot.json" not in text
    assert len(bundle["artifact_refs"]) == 9


def test_m05_is_deterministic():
    first = build_s33_m05()
    second = build_s33_m05()
    assert first["research_data_boundary_bundle"]["content_hash"] == second["research_data_boundary_bundle"]["content_hash"]
    assert first["research_boundary_preflight_report"]["bundle_hash"] == second["research_boundary_preflight_report"]["bundle_hash"]


def test_m05_propagates_blocked_operations_when_view_missing():
    m01 = build_s33_m01({"clean_option_contract_panel": None, "clean_option_quotes_panel": None})
    m02 = build_s33_m02(m01)
    m03 = build_s33_m03(m01, m02)
    m04 = build_s33_m04(m01, m03)
    out = build_s33_m05(m01, m02, m03, m04)
    blocked = out["research_data_boundary_bundle"]["blocked_operation_refs"]
    assert "options.observation.v1/get_chain_snapshot" in blocked
