from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.finalization.application.reconciliation import load_scoring_bundle
from quant_pipeline.phase_07_strategy_tournament.finalization.boundary.config import S7Config
from quant_pipeline.phase_07_strategy_tournament.finalization.errors import PolicyViolation
from quant_pipeline.phase_07_strategy_tournament.finalization.subphases.s7_safety_diversity.similarity import (
    build_similarity_graph,
    pair_similarity,
)


def _candidate_map(input_payload, s7_config):
    cfg = S7Config.model_validate(s7_config)
    bundle = load_scoring_bundle(input_payload, "TEST", cfg.forbidden_fields)
    return {candidate.candidate_id: candidate for candidate in bundle.candidates}, cfg


@pytest.mark.unit
def test_duplicate_like_candidates_have_high_similarity(input_payload, s7_config):
    candidates, cfg = _candidate_map(input_payload, s7_config)
    result = pair_similarity(candidates["A"], candidates["B"], cfg.similarity)
    assert result.score is not None
    assert result.score > 0.95
    assert result.evidence_weight_coverage == pytest.approx(1.0)


@pytest.mark.unit
def test_cross_group_pairs_are_never_materialized(input_payload, s7_config):
    candidates, cfg = _candidate_map(input_payload, s7_config)
    edges, _, _ = build_similarity_graph(tuple(candidates.values()), cfg.similarity)
    groups = {candidate.candidate_id: candidate.comparison_group_id for candidate in candidates.values()}
    assert all(groups[edge.candidate_id_left] == groups[edge.candidate_id_right] for edge in edges)


@pytest.mark.property
def test_similarity_graph_is_canonical_and_has_no_self_edges(input_payload, s7_config):
    candidates, cfg = _candidate_map(input_payload, s7_config)
    edges, summaries, _ = build_similarity_graph(tuple(reversed(tuple(candidates.values()))), cfg.similarity)
    assert all(edge.candidate_id_left < edge.candidate_id_right for edge in edges)
    assert all(edge.candidate_id_left != edge.candidate_id_right for edge in edges)
    assert len(summaries) == len(candidates)


@pytest.mark.unit
def test_missing_similarity_evidence_is_explicit(input_payload, s7_config):
    candidates, cfg = _candidate_map(input_payload, s7_config)
    left = candidates["A"]
    right = candidates["B"]
    left = left.__class__(**{**left.__dict__}) if hasattr(left, "__dict__") else left
    # frozen slots dataclass: use dataclasses.replace
    from dataclasses import replace

    result = pair_similarity(
        replace(left, payoff_shape=(), scenario_payoff=(), greek_vector=(), leg_ids=frozenset(), origin_template=None, expiration_ids=frozenset()),
        replace(right, payoff_shape=(), scenario_payoff=(), greek_vector=(), leg_ids=frozenset(), origin_template=None, expiration_ids=frozenset()),
        cfg.similarity,
    )
    assert result.score is None
    assert result.evidence_weight_coverage == 0.0


@pytest.mark.unit
def test_group_size_budget_fails_closed(input_payload, s7_config):
    candidates, cfg = _candidate_map(input_payload, s7_config)
    policy = cfg.similarity.model_copy(update={"max_group_size": 2})
    with pytest.raises(PolicyViolation) as exc_info:
        build_similarity_graph(tuple(candidates.values()), policy)
    assert exc_info.value.code == "P7_SIMILARITY_GROUP_SIZE_EXCEEDED"
