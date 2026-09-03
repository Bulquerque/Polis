from __future__ import annotations

from quant_pipeline.phase_07_strategy_tournament.tournament.s3_runner import run_subphase

from tests.tournament.tests.s3.factories import execution_config, make_bundle


def _records(result, artifact_name):
    return result["outputs"][artifact_name]["records"]


def test_economic_outputs_are_invariant_to_input_record_order():
    first = run_subphase(make_bundle(reverse_records=False), execution_config())
    second = run_subphase(make_bundle(reverse_records=True), execution_config())
    for artifact_name in (
        "comparable_candidate_metric_panel",
        "factor_adjusted_metric_panel",
        "dominance_relation_panel",
        "dominated_candidate_panel",
        "dominance_survivor_panel",
        "pareto_frontier_panel",
    ):
        assert _records(first, artifact_name) == _records(second, artifact_name)
