from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.finalization.errors import IntegrityViolation, PolicyViolation
from quant_pipeline.phase_07_strategy_tournament.finalization.runner import run_s8

from .conftest import mutate_record, permute_referenced_artifacts, rebuild, refresh_s7_manifest


def _rows(output, name):
    return output[name]["records"]


@pytest.mark.integration
def test_rank_descends_and_resets_per_group(s8_input, s8_config):
    output = run_s8(s8_input, s8_config)
    by_group = {}
    for row in _rows(output, "ranked_strategy_candidate_panel"):
        by_group.setdefault(row["comparison_group_id"], []).append(row)
    assert [row["candidate_id"] for row in sorted(by_group["G1"], key=lambda item: item["rank_position"])] == ["A", "B"]
    assert [row["rank_position"] for row in by_group["G1"]] == [1, 2]
    assert by_group["G2"][0]["candidate_id"] == "E"
    assert by_group["G2"][0]["rank_position"] == 1


@pytest.mark.property
def test_input_permutation_does_not_change_economic_outputs(s8_input, s8_config):
    original = run_s8(s8_input, s8_config)
    permuted = run_s8(permute_referenced_artifacts(s8_input), s8_config)
    for name in (
        "ranked_strategy_candidate_panel",
        "ranking_tie_report",
        "ranking_group_summary_panel",
        "strategy_thesis_card_panel",
        "ranking_trace_panel",
        "ranked_strategy_execution_context_snapshot",
        "compatibility_projection_report",
    ):
        assert original[name]["content_sha256"] == permuted[name]["content_sha256"], name


@pytest.mark.unit
def test_economic_tie_is_reported_and_candidate_id_breaks_it(s8_input, s8_config):
    a = next(row for row in s8_input["rankable_candidate_panel"]["records"] if row["candidate_id"] == "A")
    updates = {key: a[key] for key in (
        "hybrid_score", "diversity_penalty", "diversity_adjusted_score", "score_confidence",
        "robustness_stage", "execution_quality_stage", "leg_count", "pareto_tier",
    )}
    tied = mutate_record(s8_input, "rankable_candidate_panel", "B", **updates)
    output = run_s8(tied, s8_config)
    ties = _rows(output, "ranking_tie_report")
    assert len(ties) == 1
    assert ties[0]["candidate_ids"] == ["A", "B"]
    ranked = [row for row in _rows(output, "ranked_strategy_candidate_panel") if row["comparison_group_id"] == "G1"]
    assert [row["candidate_id"] for row in sorted(ranked, key=lambda item: item["rank_position"])] == ["A", "B"]


@pytest.mark.adversarial
def test_duplicate_rankable_candidate_is_rejected(s8_input, s8_config):
    payload = deepcopy(s8_input)
    rows = list(payload["rankable_candidate_panel"]["records"])
    rows.append(dict(rows[0]))
    payload["rankable_candidate_panel"] = rebuild(payload["rankable_candidate_panel"], rows)
    refresh_s7_manifest(payload)
    with pytest.raises(IntegrityViolation) as exc_info:
        run_s8(payload, s8_config)
    assert exc_info.value.code == "P7_DUPLICATE_CANDIDATE_ID"


@pytest.mark.adversarial
def test_group_budget_is_enforced(s8_input, s8_config):
    config = deepcopy(s8_config)
    config["ranking"]["max_group_size"] = 1
    with pytest.raises(PolicyViolation) as exc_info:
        run_s8(s8_input, config)
    assert exc_info.value.code == "P7_RANKING_GROUP_TOO_LARGE"
