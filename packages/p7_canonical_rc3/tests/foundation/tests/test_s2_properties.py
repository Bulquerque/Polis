from __future__ import annotations

from copy import deepcopy
import random

from quant_pipeline.phase_07_strategy_tournament.foundation.runner import run_subphase_s2
from tests.foundation.tests.conftest import make_internal_artifact, s2_candidate_record


def _run(records, feedback, registries, module_config):
    bundle = make_internal_artifact(
        "temporally_safe_candidate_bundle",
        records,
        module_config,
        grain="one_record_per_candidate",
    )
    return run_subphase_s2(
        temporally_safe_candidate_bundle=bundle,
        ranking_feedback_context=feedback,
        eligibility_policy_registry=registries["eligibility"],
        comparison_group_policy=registries["comparison"],
        metric_semantics_registry=registries["metrics"],
        objective_family_registry=registries["objectives"],
        module_config=module_config,
    )


def test_candidate_permutations_preserve_semantic_outputs(s2_inputs, module_config):
    _, feedback, registries = s2_inputs
    records = [
        s2_candidate_record("a", maximum_loss=100),
        s2_candidate_record("b", maximum_loss=200),
        s2_candidate_record("c", maximum_loss=1000),
    ]
    baseline = _run(records, feedback, registries, module_config)["outputs"]
    for seed in range(10):
        shuffled = deepcopy(records)
        random.Random(seed).shuffle(shuffled)
        current = _run(shuffled, feedback, registries, module_config)["outputs"]
        for name in (
            "eligible_strategy_candidate_panel",
            "eligibility_decision_panel",
            "candidate_comparison_group_panel",
            "candidate_metric_route_panel",
            "runtime_foundation_handoff_manifest",
        ):
            assert current[name]["content_sha256"] == baseline[name]["content_sha256"]


def test_risk_bucket_boundaries_are_left_closed(s2_inputs, module_config):
    _, feedback, registries = s2_inputs
    values = [(0, "RISK_0000_0249"), (249.999, "RISK_0000_0249"), (250, "RISK_0250_0999"), (1000, "RISK_1000_4999"), (5000, "RISK_5000_PLUS")]
    for index, (value, expected) in enumerate(values):
        result = _run([s2_candidate_record(f"c{index}", maximum_loss=value)], feedback, registries, module_config)
        record = result["outputs"]["candidate_comparison_group_panel"]["records"][0]
        assert record["capital_at_risk_bucket"] == expected


def test_input_objects_remain_unchanged(s2_inputs, module_config):
    bundle, feedback, registries = s2_inputs
    before = deepcopy((bundle, feedback, registries))
    _run(bundle["records"], feedback, registries, module_config)
    assert (bundle, feedback, registries) == before
