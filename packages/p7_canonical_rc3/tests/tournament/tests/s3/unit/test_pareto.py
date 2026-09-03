from __future__ import annotations

from quant_pipeline.phase_07_strategy_tournament.tournament.s3_runner import run_subphase

from tests.tournament.tests.s3.factories import execution_config, make_bundle


def test_frontier_and_layers_are_correct():
    result = run_subphase(make_bundle(), execution_config())
    rows = {row["candidate_id"]: row for row in result["outputs"]["pareto_frontier_panel"]["records"]}
    assert rows["A"]["frontier_layer"] == 0
    assert rows["C"]["frontier_layer"] == 0
    assert rows["B"]["frontier_layer"] == 1
    assert rows["A"]["frontier_status"] == "FRONTIER"
    assert rows["B"]["frontier_status"] == "DOMINATED_LAYER"


def test_singleton_groups_are_frontier_members():
    result = run_subphase(make_bundle(separate_groups=True), execution_config())
    rows = {row["candidate_id"]: row for row in result["outputs"]["pareto_frontier_panel"]["records"]}
    assert rows["B"]["frontier_layer"] == 0
    assert rows["B"]["frontier_status"] == "FRONTIER"
