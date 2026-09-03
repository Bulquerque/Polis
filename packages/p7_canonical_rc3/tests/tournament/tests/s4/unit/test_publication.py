from __future__ import annotations

import math

from quant_pipeline.phase_07_strategy_tournament.tournament.s4_runner import run_subphase

from tests.tournament.tests.s4.factories import execution_config, make_bundle


def test_handoff_manifest_references_s4_outputs():
    outputs = run_subphase(make_bundle(), execution_config())["outputs"]
    refs = {row["artifact_name"] for row in outputs["interpretable_tournament_handoff_manifest"]["records"][0]["references"]}
    assert {"scoring_head_panel", "interpretable_score_panel", "score_decomposition_panel", "interpretable_tournament_audit_report"}.issubset(refs)


def test_decomposition_reconciles_final_score():
    outputs = run_subphase(make_bundle(), execution_config())["outputs"]
    decomposition = outputs["score_decomposition_panel"]["records"]
    for score in outputs["interpretable_score_panel"]["records"]:
        rows = [row for row in decomposition if row["candidate_id"] == score["candidate_id"] and row["stage_type"] in {"HEAD", "PENALTY", "CONFIDENCE"}]
        assert math.isclose(sum(row["score_contribution"] for row in rows), score["final_interpretable_score"])


def test_factor_rows_are_informational_not_double_counted():
    outputs = run_subphase(make_bundle(), execution_config())["outputs"]
    rows = [row for row in outputs["score_decomposition_panel"]["records"] if row["stage_type"] == "FACTOR"]
    assert rows
    assert all(row["score_contribution"] == 0.0 for row in rows)


def test_audit_candidate_counts_are_consistent():
    audit = run_subphase(make_bundle(), execution_config())["outputs"]["interpretable_tournament_audit_report"]["records"][0]
    assert audit["input_candidate_count"] == 3
    assert audit["frontier_candidate_count"] == 2
    assert audit["dominated_candidate_count"] == 1
    assert audit["scored_candidate_count"] == 2
    assert audit["candidate_conservation_passed"] is True
