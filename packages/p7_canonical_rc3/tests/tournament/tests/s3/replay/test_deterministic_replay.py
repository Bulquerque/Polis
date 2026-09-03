from __future__ import annotations

from quant_pipeline.phase_07_strategy_tournament.tournament.s3_runner import run_subphase

from tests.tournament.tests.s3.factories import execution_config, make_bundle


def test_same_inputs_and_config_produce_identical_artifacts():
    first = run_subphase(make_bundle(), execution_config())
    second = run_subphase(make_bundle(), execution_config())
    assert first == second
