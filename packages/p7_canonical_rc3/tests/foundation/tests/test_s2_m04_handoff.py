from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S2_M04_runtime_foundation_handoff_publisher import run_module
from quant_pipeline.phase_07_strategy_tournament.foundation.runner import run_subphase_s2
from quant_pipeline.phase_07_strategy_tournament.foundation.s2_errors import P7S2Error


def full_result(s2_inputs, module_config):
    bundle, feedback, registries = s2_inputs
    return run_subphase_s2(
        temporally_safe_candidate_bundle=bundle,
        ranking_feedback_context=feedback,
        eligibility_policy_registry=registries["eligibility"],
        comparison_group_policy=registries["comparison"],
        metric_semantics_registry=registries["metrics"],
        objective_family_registry=registries["objectives"],
        module_config=module_config,
    )


def handoff_inputs(result, feedback):
    outputs = result["outputs"]
    return {
        "eligible_strategy_candidate_panel": outputs["eligible_strategy_candidate_panel"],
        "eligibility_blocked_candidate_panel": outputs["eligibility_blocked_candidate_panel"],
        "eligibility_decision_panel": outputs["eligibility_decision_panel"],
        "candidate_comparison_group_panel": outputs["candidate_comparison_group_panel"],
        "candidate_metric_route_panel": outputs["candidate_metric_route_panel"],
        "ranking_feedback_context": feedback,
    }


def test_publishes_content_addressed_foundation_handoff(s2_inputs, module_config):
    _, feedback, _ = s2_inputs
    result = full_result(s2_inputs, module_config)
    manifest = result["outputs"]["runtime_foundation_handoff_manifest"]
    record = manifest["records"][0]
    assert record["producer_stage"] == "FOUNDATION"
    assert set(record["consumer_stages"]) == {"TOURNAMENT", "LEARNING"}
    assert len(record["artifacts"]) == 6
    assert record["handoff_id"].startswith("foundation-")


def test_rejects_missing_handoff_input(s2_inputs, module_config):
    _, feedback, _ = s2_inputs
    result = full_result(s2_inputs, module_config)
    inputs = handoff_inputs(result, feedback)
    del inputs["candidate_metric_route_panel"]
    with pytest.raises(TypeError):
        run_module(inputs, module_config)


def test_rejects_hash_mismatch(s2_inputs, module_config):
    _, feedback, _ = s2_inputs
    result = full_result(s2_inputs, module_config)
    inputs = handoff_inputs(result, feedback)
    inputs["eligible_strategy_candidate_panel"]["records"][0]["underlying_id"] = "MUTATED"
    with pytest.raises(P7S2Error) as exc:
        run_module(inputs, module_config)
    assert exc.value.code == "P7_STAGE1_HANDOFF_HASH_MISMATCH"


def test_rejects_wrong_grain(s2_inputs, module_config):
    _, feedback, _ = s2_inputs
    result = full_result(s2_inputs, module_config)
    inputs = handoff_inputs(result, feedback)
    inputs["candidate_comparison_group_panel"]["grain"] = "wrong"
    _rehash(inputs["candidate_comparison_group_panel"])
    with pytest.raises(P7S2Error) as exc:
        run_module(inputs, module_config)
    assert exc.value.code == "P7_STAGE1_HANDOFF_GRAIN_MISMATCH"


def test_rejects_partition_mismatch(s2_inputs, module_config):
    _, feedback, _ = s2_inputs
    result = full_result(s2_inputs, module_config)
    inputs = handoff_inputs(result, feedback)
    blocked = deepcopy(inputs["eligible_strategy_candidate_panel"]["records"][0])
    inputs["eligibility_blocked_candidate_panel"]["records"] = [blocked]
    inputs["eligibility_blocked_candidate_panel"]["record_count"] = 1
    _rehash(inputs["eligibility_blocked_candidate_panel"])
    with pytest.raises(P7S2Error) as exc:
        run_module(inputs, module_config)
    assert exc.value.code == "P7_STAGE1_HANDOFF_INCOMPLETE"


def _rehash(artifact):
    from quant_pipeline.phase_07_strategy_tournament.foundation.canonical import content_sha256

    artifact["content_sha256"] = content_sha256({k: v for k, v in artifact.items() if k != "content_sha256"})
