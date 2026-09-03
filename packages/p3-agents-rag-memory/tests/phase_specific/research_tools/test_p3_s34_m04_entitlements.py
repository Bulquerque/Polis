from __future__ import annotations

from copy import deepcopy

from jsonschema import Draft202012Validator

from .support_s34 import build_s34_m04, gateway_policy
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import PersonToolEntitlementPanel


def _index(panel):
    return {(r["person_id"], r["tool_id"]): r for r in panel["records"]}


def _modes(record, operation_id: str) -> list[str]:
    op = next(item for item in record["operations"] if item["operation_id"] == operation_id)
    return op["arguments_schema"]["properties"]["research_mode"]["enum"]


def test_projection_is_exact_s21_contract_with_functional_operations() -> None:
    out = build_s34_m04()
    panel = PersonToolEntitlementPanel.model_validate(out["extended_person_tool_entitlement_panel"], strict=False)
    assert panel.records
    assert all(record.budget_calls_per_cycle <= 5 for record in panel.records)
    forbidden = {"DISCOVER", "REQUEST", "EXECUTE"}
    assert not forbidden.intersection({op.operation_id for record in panel.records for op in record.operations})
    for record in out["extended_person_tool_entitlement_panel"]["records"]:
        for operation in record["operations"]:
            Draft202012Validator.check_schema(operation["arguments_schema"])
            Draft202012Validator.check_schema(operation["result_schema"])


def test_personas_receive_different_modes_not_separate_tools() -> None:
    idx = _index(build_s34_m04()["extended_person_tool_entitlement_panel"])
    retail = idx[("retail-1", "research.corpus.v1")]
    institutional = idx[("institutional-1", "research.corpus.v1")]
    assert set(_modes(retail, "search")) == {"LOOKUP", "STANDARD"}
    assert set(_modes(institutional, "search")) == {"LOOKUP", "STANDARD", "TRIANGULATED", "FORENSIC"}
    assert retail["tool_id"] == institutional["tool_id"]


def test_blocked_view_removes_operation_fail_closed() -> None:
    base = build_s34_m04()
    # Rebuild using a readiness report with market history blocked.
    from .support_s33 import build_s33_m01
    from .support_s34 import build_s34_m02, build_s34_m03, legacy_entitlements, run_snapshot
    from .support import load_yaml
    from .support_s33 import s32_outputs
    from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.s34 import build_effective_entitlements
    readiness = deepcopy(build_s33_m01()["phase2_research_view_readiness_report"])
    for row in readiness["records"]:
        if row["operation_ref"] == "market.observation.v1/get_history":
            row["status"] = "BLOCKED_UPSTREAM"
    readiness["ready_count"] = sum(r["status"] == "READY" for r in readiness["records"])
    readiness["degraded_count"] = sum(r["status"] == "DEGRADED" for r in readiness["records"])
    readiness["blocked_count"] = sum(r["status"] == "BLOCKED_UPSTREAM" for r in readiness["records"])
    out = build_effective_entitlements({
        **s32_outputs(), **build_s34_m02(), **build_s34_m03(),
        "phase2_research_view_readiness_report": readiness,
        "person_tool_entitlement_panel": legacy_entitlements(),
        "research_entitlement_policy_config": load_yaml("config/research_tools/RESEARCH_ENTITLEMENT_POLICY.yaml"),
        "mcp_gateway_policy": gateway_policy(), "phase3_run_snapshot": run_snapshot(),
    })
    idx = _index(out["extended_person_tool_entitlement_panel"])
    assert "get_history" not in {op["operation_id"] for op in idx[("institutional-1", "market.observation.v1")]["operations"]}
    assert base["entitlement_resolution_audit"]["allowed_decision_count"] > out["entitlement_resolution_audit"]["allowed_decision_count"]


def test_legacy_gateway_policy_projects_without_network_authority() -> None:
    legacy = {
        "policy_version": "2.0.0",
        "global_controls": {
            "execution_context": "BACKTEST",
            "max_calls_per_person_cycle": 3,
            "hard_timeout_ms": 25000,
        },
    }
    out = build_s34_m04({"mcp_gateway_policy": legacy})
    assert all(record["budget_calls_per_cycle"] <= 3 for record in out["extended_person_tool_entitlement_panel"]["records"])
