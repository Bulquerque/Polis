from __future__ import annotations

from copy import deepcopy

from .support_s33 import build_s33_m01, p2_inputs


def test_m01_builds_all_canonical_views_without_rows():
    out = build_s33_m01()
    manifest = out["phase2_research_view_manifest"]
    assert manifest["view_count"] == 15
    assert all("records" not in view and "rows" not in view for view in manifest["views"])
    assert {view["view_class"] for view in manifest["views"]} == {
        "DOCUMENTARY", "MARKET", "MACRO", "OPTIONS", "REFERENCE"
    }


def test_m01_maps_operations_from_s32_registry():
    out = build_s33_m01()
    views = {item["artifact_name"]: item for item in out["phase2_research_view_manifest"]["views"]}
    assert "market.observation.v1/get_history" in views["clean_underlying_panel"]["allowed_operation_refs"]
    assert "research.corpus.v1/search" in views["clean_document_panel"]["allowed_operation_refs"]
    assert "macro.observation.v1/get_observations" in views["clean_macro_br_panel"]["allowed_operation_refs"]


def test_m01_missing_panel_is_granular_block_not_global_exception():
    out = build_s33_m01({"clean_option_quotes_panel": None})
    manifest = out["phase2_research_view_manifest"]
    report = out["phase2_research_view_readiness_report"]
    assert manifest["status"] == "DEGRADED"
    assert manifest["view_count"] == 14
    blocked = [item for item in report["records"] if item["view_id"] == "p2.clean_option_quotes_panel.v1"]
    assert blocked and all(item["status"] == "BLOCKED_UPSTREAM" for item in blocked)


def test_m01_quality_block_blocks_present_views():
    inputs = p2_inputs()
    inputs["quality_report_phase_2"] = deepcopy(inputs["quality_report_phase_2"])
    inputs["quality_report_phase_2"]["status"] = "BLOCK"
    out = build_s33_m01(inputs)
    assert all(item["readiness"] == "BLOCKED_UPSTREAM" for item in out["phase2_research_view_manifest"]["views"])


def test_m01_is_order_invariant():
    inputs = p2_inputs()
    reversed_inputs = dict(reversed(list(inputs.items())))
    first = build_s33_m01(inputs)
    second = build_s33_m01(reversed_inputs)
    assert first["phase2_research_view_manifest"]["content_hash"] == second["phase2_research_view_manifest"]["content_hash"]
