from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.foundation.canonical import content_sha256
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S2_M01_eligibility_policy_engine import run_module as run_m01
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S2_M02_comparison_group_builder import run_module as run_m02
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S2_M03_metric_semantics_router import run_module as run_m03
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S2_M04_runtime_foundation_handoff_publisher import run_module as run_m04
from quant_pipeline.phase_07_strategy_tournament.foundation.runner import run_subphase_s2
from quant_pipeline.phase_07_strategy_tournament.foundation.s2_errors import P7S2Error


def _rehash(artifact):
    artifact["content_sha256"] = content_sha256(
        {key: value for key, value in artifact.items() if key != "content_sha256"}
    )


def _eligible(s2_inputs, module_config):
    bundle, feedback, registries = s2_inputs
    result = run_m01(
        {
            "temporally_safe_candidate_bundle": bundle,
            "ranking_feedback_context": feedback,
            "eligibility_policy_registry": registries["eligibility"],
        },
        module_config,
    )
    return result["outputs"]["eligible_strategy_candidate_panel"], registries


def _full(s2_inputs, module_config):
    bundle, feedback, registries = s2_inputs
    result = run_subphase_s2(
        temporally_safe_candidate_bundle=bundle,
        ranking_feedback_context=feedback,
        eligibility_policy_registry=registries["eligibility"],
        comparison_group_policy=registries["comparison"],
        metric_semantics_registry=registries["metrics"],
        objective_family_registry=registries["objectives"],
        module_config=module_config,
    )
    outputs = result["outputs"]
    return {
        "eligible_strategy_candidate_panel": deepcopy(outputs["eligible_strategy_candidate_panel"]),
        "eligibility_blocked_candidate_panel": deepcopy(outputs["eligibility_blocked_candidate_panel"]),
        "eligibility_decision_panel": deepcopy(outputs["eligibility_decision_panel"]),
        "candidate_comparison_group_panel": deepcopy(outputs["candidate_comparison_group_panel"]),
        "candidate_metric_route_panel": deepcopy(outputs["candidate_metric_route_panel"]),
        "ranking_feedback_context": deepcopy(feedback),
    }, registries


def test_group_builder_rejects_bad_hash(s2_inputs, module_config):
    eligible, registries = _eligible(s2_inputs, module_config)
    eligible["records"][0]["underlying_id"] = "MUTATED"
    with pytest.raises(P7S2Error) as exc:
        run_m02(
            {"eligible_strategy_candidate_panel": eligible, "comparison_group_policy": registries["comparison"]},
            module_config,
        )
    assert exc.value.code == "P7_S2_INPUT_INVALID"


def test_group_builder_rejects_missing_key_and_negative_risk(s2_inputs, module_config):
    eligible, registries = _eligible(s2_inputs, module_config)
    missing = deepcopy(eligible)
    del missing["records"][0]["underlying_id"]
    _rehash(missing)
    with pytest.raises(P7S2Error) as exc:
        run_m02(
            {"eligible_strategy_candidate_panel": missing, "comparison_group_policy": registries["comparison"]},
            module_config,
        )
    assert exc.value.code == "P7_COMPARISON_KEY_MISSING"

    negative = deepcopy(eligible)
    negative["records"][0]["risk"]["maximum_loss"] = -1.0
    _rehash(negative)
    with pytest.raises(P7S2Error) as exc:
        run_m02(
            {"eligible_strategy_candidate_panel": negative, "comparison_group_policy": registries["comparison"]},
            module_config,
        )
    assert exc.value.code == "P7_CAPITAL_RISK_BUCKET_UNRESOLVED"


def test_group_builder_rejects_currency_missing_everywhere(s2_inputs, module_config):
    eligible, registries = _eligible(s2_inputs, module_config)
    broken = deepcopy(eligible)
    del broken["records"][0]["candidate"]["currency"]
    del broken["records"][0]["cost_liquidity"]["currency"]
    del broken["records"][0]["market_snapshot"]["currency"]
    _rehash(broken)
    with pytest.raises(P7S2Error) as exc:
        run_m02(
            {"eligible_strategy_candidate_panel": broken, "comparison_group_policy": registries["comparison"]},
            module_config,
        )
    assert exc.value.code == "P7_CURRENCY_SCOPE_MISMATCH"


def test_metric_router_rejects_unknown_candidate_family(s2_inputs, module_config):
    eligible, registries = _eligible(s2_inputs, module_config)
    groups = run_m02(
        {"eligible_strategy_candidate_panel": eligible, "comparison_group_policy": registries["comparison"]},
        module_config,
    )["outputs"]["candidate_comparison_group_panel"]
    eligible["records"][0]["objective_family"] = "NO_METRIC_CONTRACT"
    _rehash(eligible)
    with pytest.raises(P7S2Error) as exc:
        run_m03(
            {
                "eligible_strategy_candidate_panel": eligible,
                "candidate_comparison_group_panel": groups,
                "metric_semantics_registry": registries["metrics"],
                "objective_family_registry": registries["objectives"],
            },
            module_config,
        )
    assert exc.value.code == "P7_METRIC_SEMANTICS_UNKNOWN"


def test_handoff_rejects_wrong_slot_name_and_invalid_candidate_id(s2_inputs, module_config):
    inputs, _ = _full(s2_inputs, module_config)
    wrong_name = deepcopy(inputs)
    wrong_name["eligible_strategy_candidate_panel"]["artifact_name"] = "wrong"
    _rehash(wrong_name["eligible_strategy_candidate_panel"])
    with pytest.raises(P7S2Error) as exc:
        run_m04(wrong_name, module_config)
    assert exc.value.code == "P7_STAGE1_HANDOFF_INCOMPLETE"

    invalid_id = deepcopy(inputs)
    invalid_id["candidate_metric_route_panel"]["records"][0]["candidate_id"] = ""
    _rehash(invalid_id["candidate_metric_route_panel"])
    with pytest.raises(P7S2Error) as exc:
        run_m04(invalid_id, module_config)
    assert exc.value.code == "P7_STAGE1_HANDOFF_INCOMPLETE"


def test_handoff_rejects_duplicate_and_wrong_status_decisions(s2_inputs, module_config):
    inputs, _ = _full(s2_inputs, module_config)
    duplicate = deepcopy(inputs)
    duplicate["eligibility_decision_panel"]["records"].append(
        deepcopy(duplicate["eligibility_decision_panel"]["records"][0])
    )
    duplicate["eligibility_decision_panel"]["record_count"] = 2
    _rehash(duplicate["eligibility_decision_panel"])
    with pytest.raises(P7S2Error) as exc:
        run_m04(duplicate, module_config)
    assert exc.value.code == "P7_STAGE1_HANDOFF_INCOMPLETE"

    wrong_status = deepcopy(inputs)
    wrong_status["eligibility_decision_panel"]["records"][0]["status"] = "BLOCKED"
    _rehash(wrong_status["eligibility_decision_panel"])
    with pytest.raises(P7S2Error) as exc:
        run_m04(wrong_status, module_config)
    assert exc.value.code == "P7_STAGE1_HANDOFF_INCOMPLETE"
