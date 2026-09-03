from __future__ import annotations

from quant_pipeline.phase_07_strategy_tournament.tournament.s4_runner import run_subphase

from tests.tournament.tests.s4.factories import execution_config, make_bundle


def test_exact_replay_produces_identical_artifact_ids_and_hashes():
    first = run_subphase(make_bundle(), execution_config())["outputs"]
    second = run_subphase(make_bundle(), execution_config())["outputs"]
    for name in first:
        assert first[name]["artifact_id"] == second[name]["artifact_id"]
        assert first[name]["content_sha256"] == second[name]["content_sha256"]
