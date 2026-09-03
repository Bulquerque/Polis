from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S2_M01_eligibility_policy_engine import run_module as run_m01
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S2_M02_comparison_group_builder import run_module as run_m02
from quant_pipeline.phase_07_strategy_tournament.foundation.s2_errors import P7S2Error
from tests.foundation.tests.conftest import make_internal_artifact, s2_candidate_record


def eligible_panel(bundle, feedback, registries, module_config):
    return run_m01(
        {
            "temporally_safe_candidate_bundle": bundle,
            "ranking_feedback_context": feedback,
            "eligibility_policy_registry": registries["eligibility"],
        },
        module_config,
    )["outputs"]["eligible_strategy_candidate_panel"]


def test_group_id_is_deterministic_and_query_id_matches(s2_inputs, module_config):
    bundle, feedback, registries = s2_inputs
    eligible = eligible_panel(bundle, feedback, registries, module_config)
    first = run_m02(
        {"eligible_strategy_candidate_panel": eligible, "comparison_group_policy": registries["comparison"]},
        module_config,
    )
    second = run_m02(
        {"eligible_strategy_candidate_panel": eligible, "comparison_group_policy": registries["comparison"]},
        module_config,
    )
    a = first["outputs"]["candidate_comparison_group_panel"]
    b = second["outputs"]["candidate_comparison_group_panel"]
    assert a["content_sha256"] == b["content_sha256"]
    assert a["records"][0]["comparison_group_id"] == a["records"][0]["query_id"]
    assert a["records"][0]["capital_at_risk_bucket"] == "RISK_0000_0249"


def test_same_economic_dimensions_share_group(s2_inputs, module_config):
    _, feedback, registries = s2_inputs
    bundle = make_internal_artifact(
        "temporally_safe_candidate_bundle",
        [s2_candidate_record("a"), s2_candidate_record("b", maximum_loss=200.0)],
        module_config,
        grain="one_record_per_candidate",
    )
    eligible = eligible_panel(bundle, feedback, registries, module_config)
    result = run_m02(
        {"eligible_strategy_candidate_panel": eligible, "comparison_group_policy": registries["comparison"]},
        module_config,
    )
    records = result["outputs"]["candidate_comparison_group_panel"]["records"]
    assert len({r["comparison_group_id"] for r in records}) == 1
    assert all(r["group_size"] == 2 for r in records)


def test_risk_bucket_separates_otherwise_equal_candidates(s2_inputs, module_config):
    _, feedback, registries = s2_inputs
    bundle = make_internal_artifact(
        "temporally_safe_candidate_bundle",
        [s2_candidate_record("a", maximum_loss=100.0), s2_candidate_record("b", maximum_loss=1000.0)],
        module_config,
        grain="one_record_per_candidate",
    )
    eligible = eligible_panel(bundle, feedback, registries, module_config)
    result = run_m02(
        {"eligible_strategy_candidate_panel": eligible, "comparison_group_policy": registries["comparison"]},
        module_config,
    )
    assert len({r["comparison_group_id"] for r in result["outputs"]["candidate_comparison_group_panel"]["records"]}) == 2


def test_rejects_currency_disagreement(s2_inputs, module_config):
    bundle, feedback, registries = deepcopy(s2_inputs)
    bundle["records"][0]["cost_liquidity"]["currency"] = "BRL"
    _rehash(bundle)
    eligible = eligible_panel(bundle, feedback, registries, module_config)
    with pytest.raises(P7S2Error) as exc:
        run_m02(
            {"eligible_strategy_candidate_panel": eligible, "comparison_group_policy": registries["comparison"]},
            module_config,
        )
    assert exc.value.code == "P7_CURRENCY_SCOPE_MISMATCH"


def test_permutation_does_not_change_group_artifact(s2_inputs, module_config):
    _, feedback, registries = s2_inputs
    records = [s2_candidate_record("a"), s2_candidate_record("b")]
    bundle_a = make_internal_artifact(
        "temporally_safe_candidate_bundle", records, module_config, grain="one_record_per_candidate"
    )
    bundle_b = make_internal_artifact(
        "temporally_safe_candidate_bundle", list(reversed(records)), module_config, grain="one_record_per_candidate"
    )
    outputs = []
    for bundle in (bundle_a, bundle_b):
        eligible = eligible_panel(bundle, feedback, registries, module_config)
        groups = run_m02(
            {"eligible_strategy_candidate_panel": eligible, "comparison_group_policy": registries["comparison"]},
            module_config,
        )["outputs"]["candidate_comparison_group_panel"]
        outputs.append(groups)
    assert outputs[0]["content_sha256"] == outputs[1]["content_sha256"]


def _rehash(artifact):
    from quant_pipeline.phase_07_strategy_tournament.foundation.canonical import content_sha256

    artifact["content_sha256"] = content_sha256({k: v for k, v in artifact.items() if k != "content_sha256"})
