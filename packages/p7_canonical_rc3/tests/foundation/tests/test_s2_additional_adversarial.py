from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S2_M01_eligibility_policy_engine import run_module as run_m01
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S2_M02_comparison_group_builder import run_module as run_m02
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S2_M03_metric_semantics_router import run_module as run_m03
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S2_M04_runtime_foundation_handoff_publisher import run_module as run_m04
from quant_pipeline.phase_07_strategy_tournament.foundation.runner import run_subphase_s2
from quant_pipeline.phase_07_strategy_tournament.foundation.s2_errors import P7S2Error
from tests.foundation.tests.conftest import make_internal_artifact, s2_candidate_record


def _rehash(artifact):
    from quant_pipeline.phase_07_strategy_tournament.foundation.canonical import content_sha256

    artifact["content_sha256"] = content_sha256({k: v for k, v in artifact.items() if k != "content_sha256"})


def _m01(s2_inputs, module_config):
    bundle, feedback, registries = s2_inputs
    return run_m01(
        {
            "temporally_safe_candidate_bundle": bundle,
            "ranking_feedback_context": feedback,
            "eligibility_policy_registry": registries["eligibility"],
        },
        module_config,
    )


def test_invalid_active_policy_is_fatal(s2_inputs, module_config):
    bundle, feedback, registries = deepcopy(s2_inputs)
    registries["eligibility"]["active_policy_id"] = "missing"
    with pytest.raises(P7S2Error) as exc:
        run_m01(
            {
                "temporally_safe_candidate_bundle": bundle,
                "ranking_feedback_context": feedback,
                "eligibility_policy_registry": registries["eligibility"],
            },
            module_config,
        )
    assert exc.value.code == "P7_ELIGIBILITY_POLICY_INVALID"


def test_missing_currency_and_stale_snapshot_are_candidate_blocks(s2_inputs, module_config):
    bundle, feedback, registries = deepcopy(s2_inputs)
    record = bundle["records"][0]
    del record["candidate"]["currency"]
    record["market_snapshot"]["market_snapshot_time"] = "2026-01-05T12:00:00Z"
    _rehash(bundle)
    result = run_m01(
        {
            "temporally_safe_candidate_bundle": bundle,
            "ranking_feedback_context": feedback,
            "eligibility_policy_registry": registries["eligibility"],
        },
        module_config,
    )
    reasons = set(result["outputs"]["eligibility_decision_panel"]["records"][0]["reason_codes"])
    assert "P7_REQUIRED_METRIC_UNAVAILABLE" in reasons
    assert "P7_CURRENCY_UNSUPPORTED" in reasons
    assert "P7_MARKET_SNAPSHOT_STALE" in reasons


def test_non_representative_equivalence_is_blocked(s2_inputs, module_config):
    bundle, feedback, registries = deepcopy(s2_inputs)
    record = bundle["records"][0]
    record["equivalence"] = [{"candidate_id": "cand-1", "representative_candidate_id": "cand-0"}]
    _rehash(bundle)
    result = run_m01(
        {
            "temporally_safe_candidate_bundle": bundle,
            "ranking_feedback_context": feedback,
            "eligibility_policy_registry": registries["eligibility"],
        },
        module_config,
    )
    assert "P7_DUPLICATE_NON_REPRESENTATIVE" in result["outputs"]["eligibility_decision_panel"]["records"][0]["reason_codes"]


def test_duplicate_candidate_id_is_fatal(s2_inputs, module_config):
    _, feedback, registries = s2_inputs
    bundle = make_internal_artifact(
        "temporally_safe_candidate_bundle",
        [s2_candidate_record("dup"), s2_candidate_record("dup")],
        module_config,
        grain="one_record_per_candidate",
    )
    with pytest.raises(P7S2Error) as exc:
        run_m01(
            {
                "temporally_safe_candidate_bundle": bundle,
                "ranking_feedback_context": feedback,
                "eligibility_policy_registry": registries["eligibility"],
            },
            module_config,
        )
    assert exc.value.code == "P7_S2_INPUT_INVALID"


def test_unsupported_horizon_is_fatal_after_eligibility(s2_inputs, module_config):
    bundle, feedback, registries = deepcopy(s2_inputs)
    bundle["records"][0]["horizon"] = "999_sessions"
    bundle["records"][0]["candidate"]["horizon"] = "999_sessions"
    _rehash(bundle)
    eligible = run_m01(
        {
            "temporally_safe_candidate_bundle": bundle,
            "ranking_feedback_context": feedback,
            "eligibility_policy_registry": registries["eligibility"],
        },
        module_config,
    )["outputs"]["eligible_strategy_candidate_panel"]
    with pytest.raises(P7S2Error) as exc:
        run_m02(
            {"eligible_strategy_candidate_panel": eligible, "comparison_group_policy": registries["comparison"]},
            module_config,
        )
    assert exc.value.code == "P7_HORIZON_UNSUPPORTED"


def test_capital_at_risk_falls_back_to_margin(s2_inputs, module_config):
    bundle, feedback, registries = deepcopy(s2_inputs)
    record = bundle["records"][0]
    del record["risk"]["maximum_loss"]
    record["risk"]["margin_estimate"] = 300.0
    eligibility = deepcopy(registries["eligibility"])
    policy = eligibility["policies"][0]
    policy["defined_risk_required"] = False
    policy["require_maximum_loss_proven"] = False
    policy["required_metric_paths_by_objective"]["RANGE"] = [
        path for path in policy["required_metric_paths_by_objective"]["RANGE"] if path != "risk.maximum_loss"
    ]
    _rehash(bundle)
    eligible = run_m01(
        {
            "temporally_safe_candidate_bundle": bundle,
            "ranking_feedback_context": feedback,
            "eligibility_policy_registry": eligibility,
        },
        module_config,
    )["outputs"]["eligible_strategy_candidate_panel"]
    groups = run_m02(
        {"eligible_strategy_candidate_panel": eligible, "comparison_group_policy": registries["comparison"]},
        module_config,
    )["outputs"]["candidate_comparison_group_panel"]
    assert groups["records"][0]["capital_at_risk_source"] == "risk.margin_estimate"
    assert groups["records"][0]["capital_at_risk_bucket"] == "RISK_0250_0999"


def test_invalid_comparison_bucket_registry_is_rejected(s2_inputs, module_config):
    result = _m01(s2_inputs, module_config)
    _, _, registries = deepcopy(s2_inputs)
    registry = registries["comparison"]
    registry["policies"][0]["risk_buckets"][0]["upper_exclusive"] = 200
    with pytest.raises(P7S2Error) as exc:
        run_m02(
            {
                "eligible_strategy_candidate_panel": result["outputs"]["eligible_strategy_candidate_panel"],
                "comparison_group_policy": registry,
            },
            module_config,
        )
    assert exc.value.code == "P7_COMPARISON_GROUP_POLICY_INVALID"


def test_nonfinite_metric_is_rejected_by_router(s2_inputs, module_config):
    result = _m01(s2_inputs, module_config)
    eligible = result["outputs"]["eligible_strategy_candidate_panel"]
    _, _, registries = s2_inputs
    groups = run_m02(
        {"eligible_strategy_candidate_panel": eligible, "comparison_group_policy": registries["comparison"]},
        module_config,
    )["outputs"]["candidate_comparison_group_panel"]
    broken = deepcopy(eligible)
    broken["records"][0]["risk"]["expected_net_payoff"] = float("inf")
    # Pydantic rejects non-finite values at hashing / wire validation boundary.
    with pytest.raises((ValueError, P7S2Error)):
        run_m03(
            {
                "eligible_strategy_candidate_panel": broken,
                "candidate_comparison_group_panel": groups,
                "metric_semantics_registry": registries["metrics"],
                "objective_family_registry": registries["objectives"],
            },
            module_config,
        )


def test_empty_universe_publishes_valid_empty_handoff(s2_inputs, module_config):
    _, feedback, registries = s2_inputs
    bundle = make_internal_artifact(
        "temporally_safe_candidate_bundle", [], module_config, grain="one_record_per_candidate"
    )
    result = run_subphase_s2(
        temporally_safe_candidate_bundle=bundle,
        ranking_feedback_context=feedback,
        eligibility_policy_registry=registries["eligibility"],
        comparison_group_policy=registries["comparison"],
        metric_semantics_registry=registries["metrics"],
        objective_family_registry=registries["objectives"],
        module_config=module_config,
    )
    assert result["outputs"]["candidate_metric_route_panel"]["record_count"] == 0
    assert result["outputs"]["runtime_foundation_handoff_manifest"]["record_count"] == 1


def test_handoff_context_mismatch_is_rejected(s2_inputs, module_config):
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
    inputs = {
        "eligible_strategy_candidate_panel": result["outputs"]["eligible_strategy_candidate_panel"],
        "eligibility_blocked_candidate_panel": result["outputs"]["eligibility_blocked_candidate_panel"],
        "eligibility_decision_panel": result["outputs"]["eligibility_decision_panel"],
        "candidate_comparison_group_panel": result["outputs"]["candidate_comparison_group_panel"],
        "candidate_metric_route_panel": result["outputs"]["candidate_metric_route_panel"],
        "ranking_feedback_context": deepcopy(feedback),
    }
    inputs["ranking_feedback_context"]["run_id"] = "other"
    _rehash(inputs["ranking_feedback_context"])
    with pytest.raises(P7S2Error) as exc:
        run_m04(inputs, module_config)
    assert exc.value.code == "P7_STAGE1_HANDOFF_INCOMPLETE"


def test_wrappers_reject_wrong_shapes(module_config):
    with pytest.raises(TypeError):
        run_m01({}, module_config)
    with pytest.raises(TypeError):
        run_m02({}, module_config)
    with pytest.raises(TypeError):
        run_m03({}, module_config)
    with pytest.raises(TypeError):
        run_m04({}, module_config)
