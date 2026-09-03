from __future__ import annotations

import pytest

from quant_pipeline.phase_07_strategy_tournament.tournament.domain.errors import PolicyViolation
from quant_pipeline.phase_07_strategy_tournament.tournament.modules.P7_S4_M01_scoring_policy_head_binding_compiler import run_module

from tests.tournament.tests.s4.factories import execution_config, make_bundle, scoring_policy, scoring_rule


def test_binding_selects_only_frontier_candidates():
    result = run_module(make_bundle(), execution_config())
    records = result["outputs"]["scoring_head_input_panel"]["records"]
    assert {row["candidate_id"] for row in records} == {"A", "C"}


def test_binding_resolves_objective_specific_rule():
    policy = scoring_policy(rules=(scoring_rule(rule_id="wild", objective_families=("*",)), scoring_rule(rule_id="specific")))
    result = run_module(make_bundle(policy=policy), execution_config())
    receipt = result["outputs"]["scoring_policy_receipt"]["records"][0]
    assert {row["rule_id"] for row in receipt["resolutions"]} == {"specific"}


def test_binding_rejects_ambiguous_equal_specificity():
    policy = scoring_policy(rules=(scoring_rule(rule_id="one"), scoring_rule(rule_id="two")))
    with pytest.raises(PolicyViolation) as exc:
        run_module(make_bundle(policy=policy), execution_config())
    assert exc.value.code == "P7_S4_SCORING_POLICY_AMBIGUOUS"


def test_binding_can_include_additional_pareto_layer_by_policy():
    policy = scoring_policy(rules=(scoring_rule(max_layer=1),))
    result = run_module(make_bundle(policy=policy), execution_config())
    receipt = result["outputs"]["scoring_policy_receipt"]["records"][0]
    assert receipt["selected_candidate_count"] == 3


def test_policy_hash_is_deterministic():
    first = run_module(make_bundle(), execution_config())
    second = run_module(make_bundle(reverse_records=True), execution_config())
    hash_a = first["outputs"]["scoring_policy_receipt"]["records"][0]["policy_hash"]
    hash_b = second["outputs"]["scoring_policy_receipt"]["records"][0]["policy_hash"]
    assert hash_a == hash_b
