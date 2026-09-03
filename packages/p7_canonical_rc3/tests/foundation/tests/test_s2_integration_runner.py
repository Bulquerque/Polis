from copy import deepcopy

from quant_pipeline.phase_07_strategy_tournament.foundation.canonical import content_sha256
from quant_pipeline.phase_07_strategy_tournament.foundation.runner import run_subphase_s1, run_subphase_s2


def test_s1_to_s2_end_to_end(p6_fixture, module_config, s2_registries):
    manifest, artifacts = deepcopy(p6_fixture)
    by_name = {item["artifact_name"]: item for item in artifacts}
    candidate = by_name["strategy_candidate_panel"]["records"][0]
    candidate["currency"] = "USD"
    risk = by_name["strategy_risk_panel"]["records"][0]
    risk.update(
        {
            "maximum_loss_proven": True,
            "expected_net_payoff": 12.0,
            "expected_net_payoff_units": "currency",
            "expected_shortfall": 25.0,
            "expected_shortfall_units": "currency",
            "probability_of_profit": 0.62,
            "probability_of_profit_units": "probability",
            "return_on_max_loss": 0.12,
            "return_on_max_loss_units": "ratio",
            "maximum_loss_units": "currency",
        }
    )
    cost = by_name["strategy_cost_liquidity_panel"]["records"][0]
    cost.update(
        {
            "currency": "USD",
            "entry_cost_units": "currency",
            "liquidity_score": 0.8,
            "liquidity_score_units": "normalized_score",
        }
    )
    snapshot = by_name["strategy_market_snapshot"]["records"][0]
    snapshot.update({"currency": "USD", "calendar_id": "XNYS"})
    scenarios = by_name["strategy_scenario_evaluation_panel"]
    scenarios["records"].append({**scenarios["records"][0], "scenario_id": "scenario-2"})
    scenarios["record_count"] = 2
    for artifact in artifacts:
        artifact["content_sha256"] = content_sha256({k: v for k, v in artifact.items() if k != "content_sha256"})
        ref = next(item for item in manifest["artifacts"] if item["artifact_name"] == artifact["artifact_name"])
        ref["content_sha256"] = artifact["content_sha256"]
        ref["record_count"] = artifact["record_count"]
    s1 = run_subphase_s1(
        phase6_manifest=manifest,
        phase6_artifacts=artifacts,
        module_config=module_config,
    )
    s2 = run_subphase_s2(
        temporally_safe_candidate_bundle=s1["outputs"]["temporally_safe_candidate_bundle"],
        ranking_feedback_context=s1["outputs"]["ranking_feedback_context"],
        eligibility_policy_registry=s2_registries["eligibility"],
        comparison_group_policy=s2_registries["comparison"],
        metric_semantics_registry=s2_registries["metrics"],
        objective_family_registry=s2_registries["objectives"],
        module_config=module_config,
    )
    assert s2["outputs"]["eligible_strategy_candidate_panel"]["record_count"] == 1
    assert s2["outputs"]["candidate_comparison_group_panel"]["record_count"] == 1
    assert s2["outputs"]["candidate_metric_route_panel"]["record_count"] >= 6
    assert s2["outputs"]["runtime_foundation_handoff_manifest"]["record_count"] == 1
