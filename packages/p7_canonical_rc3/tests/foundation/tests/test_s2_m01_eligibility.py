from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.foundation.artifacts import create_artifact
from quant_pipeline.phase_07_strategy_tournament.foundation.models import ModuleContext
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S2_M01_eligibility_policy_engine import run_module
from quant_pipeline.phase_07_strategy_tournament.foundation.s2_errors import P7S2Error
from tests.foundation.tests.conftest import make_internal_artifact, s2_candidate_record


def test_eligibility_happy_path(s2_inputs, module_config):
    bundle, feedback, registries = s2_inputs
    result = run_module(
        {
            "temporally_safe_candidate_bundle": bundle,
            "ranking_feedback_context": feedback,
            "eligibility_policy_registry": registries["eligibility"],
        },
        module_config,
    )
    assert result["outputs"]["eligible_strategy_candidate_panel"]["record_count"] == 1
    assert result["outputs"]["eligibility_blocked_candidate_panel"]["record_count"] == 0
    decision = result["outputs"]["eligibility_decision_panel"]["records"][0]
    assert decision["status"] == "ELIGIBLE"
    assert decision["reason_codes"] == []


def test_blocks_unsupported_objective_without_dropping_candidate(s2_inputs, module_config):
    bundle, feedback, registries = deepcopy(s2_inputs)
    bundle["records"][0]["candidate"]["objective_family"] = "UNKNOWN"
    bundle["records"][0]["objective_family"] = "UNKNOWN"
    _rehash(bundle)
    result = run_module(
        {
            "temporally_safe_candidate_bundle": bundle,
            "ranking_feedback_context": feedback,
            "eligibility_policy_registry": registries["eligibility"],
        },
        module_config,
    )
    assert result["outputs"]["eligible_strategy_candidate_panel"]["record_count"] == 0
    assert result["outputs"]["eligibility_blocked_candidate_panel"]["record_count"] == 1
    decision = result["outputs"]["eligibility_decision_panel"]["records"][0]
    assert "P7_OBJECTIVE_FAMILY_UNSUPPORTED" in decision["reason_codes"]


def test_blocks_undefined_risk_and_insufficient_scenarios(s2_inputs, module_config):
    bundle, feedback, registries = deepcopy(s2_inputs)
    record = bundle["records"][0]
    record["risk"]["maximum_loss_proven"] = False
    record["scenario_evaluations"] = []
    _rehash(bundle)
    result = run_module(
        {
            "temporally_safe_candidate_bundle": bundle,
            "ranking_feedback_context": feedback,
            "eligibility_policy_registry": registries["eligibility"],
        },
        module_config,
    )
    reasons = set(result["outputs"]["eligibility_decision_panel"]["records"][0]["reason_codes"])
    assert "P7_DEFINED_RISK_REQUIRED" in reasons
    assert "P7_SCENARIO_COVERAGE_INSUFFICIENT" in reasons


def test_feedback_can_change_only_whitelisted_threshold(s2_inputs, module_config):
    bundle, _, registries = deepcopy(s2_inputs)
    context = ModuleContext.model_validate(module_config["context"])
    feedback = create_artifact(
        artifact_name="ranking_feedback_context",
        records=[
            {
                "feedback_id": "fb-1",
                "adjustments": [
                    {
                        "adjustment_type": "ELIGIBILITY_THRESHOLD",
                        "parameter": "min_scenario_count",
                        "value": 3,
                    }
                ],
            }
        ],
        producer_module_id="P7.S1.M04",
        context=context,
        grain="one_record_per_promoted_feedback_item",
    ).model_dump(mode="json")
    result = run_module(
        {
            "temporally_safe_candidate_bundle": bundle,
            "ranking_feedback_context": feedback,
            "eligibility_policy_registry": registries["eligibility"],
        },
        module_config,
    )
    decision = result["outputs"]["eligibility_decision_panel"]["records"][0]
    assert "P7_SCENARIO_COVERAGE_INSUFFICIENT" in decision["reason_codes"]
    audit = result["outputs"]["eligibility_policy_audit"]["records"][0]
    assert audit["applied_feedback_adjustments"][0]["parameter"] == "min_scenario_count"


def test_rejects_conflicting_feedback_policy_changes(s2_inputs, module_config):
    bundle, _, registries = deepcopy(s2_inputs)
    feedback = make_internal_artifact(
        "ranking_feedback_context",
        [
            {
                "feedback_id": "fb-1",
                "adjustments": [{"adjustment_type": "ELIGIBILITY_THRESHOLD", "parameter": "min_scenario_count", "value": 1}],
            },
            {
                "feedback_id": "fb-2",
                "adjustments": [{"adjustment_type": "ELIGIBILITY_THRESHOLD", "parameter": "min_scenario_count", "value": 2}],
            },
        ],
        module_config,
        grain="one_record_per_promoted_feedback_item",
    )
    with pytest.raises(P7S2Error) as exc:
        run_module(
            {
                "temporally_safe_candidate_bundle": bundle,
                "ranking_feedback_context": feedback,
                "eligibility_policy_registry": registries["eligibility"],
            },
            module_config,
        )
    assert exc.value.code == "P7_ELIGIBILITY_POLICY_INVALID"


def test_empty_candidate_universe_is_valid(s2_inputs, module_config):
    _, feedback, registries = s2_inputs
    bundle = make_internal_artifact(
        "temporally_safe_candidate_bundle", [], module_config, grain="one_record_per_candidate"
    )
    result = run_module(
        {
            "temporally_safe_candidate_bundle": bundle,
            "ranking_feedback_context": feedback,
            "eligibility_policy_registry": registries["eligibility"],
        },
        module_config,
    )
    assert result["outputs"]["eligibility_decision_panel"]["records"] == []
    assert result["outputs"]["eligibility_policy_audit"]["records"][0]["candidate_count"] == 0


def test_partition_conserves_multiple_candidates(s2_inputs, module_config):
    _, feedback, registries = s2_inputs
    records = [s2_candidate_record("a"), s2_candidate_record("b", objective_family="UNKNOWN")]
    bundle = make_internal_artifact(
        "temporally_safe_candidate_bundle", records, module_config, grain="one_record_per_candidate"
    )
    result = run_module(
        {
            "temporally_safe_candidate_bundle": bundle,
            "ranking_feedback_context": feedback,
            "eligibility_policy_registry": registries["eligibility"],
        },
        module_config,
    )
    eligible = {r["candidate_id"] for r in result["outputs"]["eligible_strategy_candidate_panel"]["records"]}
    blocked = {r["candidate_id"] for r in result["outputs"]["eligibility_blocked_candidate_panel"]["records"]}
    decisions = {r["candidate_id"] for r in result["outputs"]["eligibility_decision_panel"]["records"]}
    assert eligible | blocked == decisions == {"a", "b"}
    assert not eligible & blocked


def _rehash(artifact):
    from quant_pipeline.phase_07_strategy_tournament.foundation.canonical import content_sha256

    artifact["content_sha256"] = content_sha256({k: v for k, v in artifact.items() if k != "content_sha256"})
