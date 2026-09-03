from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S2_M01_eligibility_policy_engine import run_module as run_m01
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S2_M02_comparison_group_builder import run_module as run_m02
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S2_M03_metric_semantics_router import run_module as run_m03
from quant_pipeline.phase_07_strategy_tournament.foundation.s2_errors import P7S2Error


def upstream(s2_inputs, module_config):
    bundle, feedback, registries = s2_inputs
    m01 = run_m01(
        {
            "temporally_safe_candidate_bundle": bundle,
            "ranking_feedback_context": feedback,
            "eligibility_policy_registry": registries["eligibility"],
        },
        module_config,
    )
    eligible = m01["outputs"]["eligible_strategy_candidate_panel"]
    groups = run_m02(
        {"eligible_strategy_candidate_panel": eligible, "comparison_group_policy": registries["comparison"]},
        module_config,
    )["outputs"]["candidate_comparison_group_panel"]
    return eligible, groups, registries


def test_routes_required_and_optional_metrics(s2_inputs, module_config):
    eligible, groups, registries = upstream(s2_inputs, module_config)
    result = run_m03(
        {
            "eligible_strategy_candidate_panel": eligible,
            "candidate_comparison_group_panel": groups,
            "metric_semantics_registry": registries["metrics"],
            "objective_family_registry": registries["objectives"],
        },
        module_config,
    )
    routes = result["outputs"]["candidate_metric_route_panel"]["records"]
    by_id = {r["metric_id"]: r for r in routes}
    assert by_id["maximum_loss"]["direction"] == "MINIMIZE"
    assert by_id["expected_net_payoff"]["direction"] == "MAXIMIZE"
    assert by_id["worst_ambiguity_utility"]["status"] == "UNAVAILABLE"
    assert all(r["comparison_group_id"] == groups["records"][0]["comparison_group_id"] for r in routes)


def test_rejects_required_metric_missing_after_eligibility_contract(s2_inputs, module_config):
    eligible, groups, registries = upstream(s2_inputs, module_config)
    broken = deepcopy(eligible)
    del broken["records"][0]["risk"]["expected_net_payoff"]
    _rehash(broken)
    with pytest.raises(P7S2Error) as exc:
        run_m03(
            {
                "eligible_strategy_candidate_panel": broken,
                "candidate_comparison_group_panel": groups,
                "metric_semantics_registry": registries["metrics"],
                "objective_family_registry": registries["objectives"],
            },
            module_config,
        )
    assert exc.value.code == "P7_REQUIRED_METRIC_ROUTE_MISSING"


def test_rejects_metric_unit_conflict(s2_inputs, module_config):
    eligible, groups, registries = upstream(s2_inputs, module_config)
    broken = deepcopy(eligible)
    broken["records"][0]["risk"]["maximum_loss_units"] = "ratio"
    _rehash(broken)
    with pytest.raises(P7S2Error) as exc:
        run_m03(
            {
                "eligible_strategy_candidate_panel": broken,
                "candidate_comparison_group_panel": groups,
                "metric_semantics_registry": registries["metrics"],
                "objective_family_registry": registries["objectives"],
            },
            module_config,
        )
    assert exc.value.code == "P7_METRIC_UNIT_INCOMPATIBLE"


def test_rejects_unknown_metric_referenced_by_objective(s2_inputs, module_config):
    eligible, groups, registries = upstream(s2_inputs, module_config)
    objectives = deepcopy(registries["objectives"])
    objectives["families"][0]["required_metric_ids"].append("unknown_metric")
    with pytest.raises(P7S2Error) as exc:
        run_m03(
            {
                "eligible_strategy_candidate_panel": eligible,
                "candidate_comparison_group_panel": groups,
                "metric_semantics_registry": registries["metrics"],
                "objective_family_registry": objectives,
            },
            module_config,
        )
    assert exc.value.code == "P7_METRIC_SEMANTICS_UNKNOWN"


def test_candidate_and_group_sets_must_reconcile(s2_inputs, module_config):
    eligible, groups, registries = upstream(s2_inputs, module_config)
    broken = deepcopy(groups)
    broken["records"] = []
    broken["record_count"] = 0
    _rehash(broken)
    with pytest.raises(P7S2Error) as exc:
        run_m03(
            {
                "eligible_strategy_candidate_panel": eligible,
                "candidate_comparison_group_panel": broken,
                "metric_semantics_registry": registries["metrics"],
                "objective_family_registry": registries["objectives"],
            },
            module_config,
        )
    assert exc.value.code == "P7_REQUIRED_METRIC_ROUTE_MISSING"


def _rehash(artifact):
    from quant_pipeline.phase_07_strategy_tournament.foundation.canonical import content_sha256

    artifact["content_sha256"] = content_sha256({k: v for k, v in artifact.items() if k != "content_sha256"})
