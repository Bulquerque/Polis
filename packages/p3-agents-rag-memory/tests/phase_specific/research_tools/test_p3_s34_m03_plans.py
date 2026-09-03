from __future__ import annotations

from copy import deepcopy
import pytest

from .support import load_yaml
from .support_s33 import build_s33_m01
from .support_s34 import build_s34_m03
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.core.errors import ResearchToolContractError


def test_eight_plans_are_acyclic_and_bounded() -> None:
    out = build_s34_m03()
    plans = out["research_plan_registry"]["plans"]
    assert len(plans) == 8
    for plan in plans:
        assert sum(node["visible_call_cost"] for node in plan["nodes"]) <= 5
        assert plan["maximum_visible_calls_per_cycle"] <= 5
    deps = out["research_plan_dependency_matrix"]["records"]
    assert len(deps) == sum(len(plan["nodes"]) for plan in plans)


def test_current_fixtures_make_all_plans_ready() -> None:
    report = build_s34_m03()["research_plan_readiness_report"]
    assert len(report["ready_plan_ids"]) == 8
    assert report["blocked_plan_ids"] == []


def test_missing_required_view_blocks_affected_plans() -> None:
    s33 = build_s33_m01({"clean_financial_statement_panel": None})
    # Current P2 fixture has no structured statements by design; force the readiness record blocked directly.
    readiness = deepcopy(s33["phase2_research_view_readiness_report"])
    for row in readiness["records"]:
        if row["operation_ref"] == "company.fundamentals.v1/get_financial_statements":
            row["status"] = "BLOCKED_UPSTREAM"
    readiness["ready_count"] = sum(r["status"] == "READY" for r in readiness["records"])
    readiness["degraded_count"] = sum(r["status"] == "DEGRADED" for r in readiness["records"])
    readiness["blocked_count"] = sum(r["status"] == "BLOCKED_UPSTREAM" for r in readiness["records"])
    out = build_s34_m03({"phase2_research_view_readiness_report": readiness})
    assert "STANDARD_COMPANY_REVIEW" in out["research_plan_readiness_report"]["blocked_plan_ids"]


def test_cycle_is_rejected() -> None:
    cfg = deepcopy(load_yaml("config/research_tools/RESEARCH_PLAN_REGISTRY.yaml"))
    cfg["plans"][0]["nodes"][0]["predecessors"] = [cfg["plans"][0]["nodes"][1]["node_id"]]
    with pytest.raises(ResearchToolContractError) as exc:
        build_s34_m03({"research_plan_registry_config": cfg})
    assert exc.value.reason_code == "P3RT-CONTRACT-3421"
