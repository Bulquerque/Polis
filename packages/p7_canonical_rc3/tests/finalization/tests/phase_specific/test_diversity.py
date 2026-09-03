from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.finalization.application.reconciliation import load_scoring_bundle
from quant_pipeline.phase_07_strategy_tournament.finalization.boundary.config import S7Config
from quant_pipeline.phase_07_strategy_tournament.finalization.boundary.outputs import SimilarityEdgeRecord
from quant_pipeline.phase_07_strategy_tournament.finalization.errors import IntegrityViolation
from quant_pipeline.phase_07_strategy_tournament.finalization.subphases.s7_safety_diversity.diversity import adjust_diversity
from quant_pipeline.phase_07_strategy_tournament.finalization.subphases.s7_safety_diversity.similarity import build_similarity_graph


def _bundle(input_payload, s7_config):
    cfg = S7Config.model_validate(s7_config)
    return load_scoring_bundle(input_payload, "TEST", cfg.forbidden_fields), cfg


@pytest.mark.unit
def test_similar_candidates_share_cluster_and_are_penalized(input_payload, s7_config):
    bundle, cfg = _bundle(input_payload, s7_config)
    edges, _, _ = build_similarity_graph(bundle.candidates, cfg.similarity)
    clusters, adjustments, scores = adjust_diversity(bundle.candidates, edges, cfg.diversity)
    cluster_map = {record.candidate_id: record.diversity_cluster_id for record in clusters}
    penalty_map = {record.candidate_id: record.applied_penalty for record in adjustments}
    score_map = {record.candidate_id: record for record in scores}
    assert cluster_map["A"] == cluster_map["B"]
    assert penalty_map["A"] > 0
    assert score_map["A"].diversity_adjusted_score <= score_map["A"].hybrid_score


@pytest.mark.unit
def test_diversity_penalty_is_bounded(input_payload, s7_config):
    bundle, cfg = _bundle(input_payload, s7_config)
    edges, _, _ = build_similarity_graph(bundle.candidates, cfg.similarity)
    _, adjustments, _ = adjust_diversity(bundle.candidates, edges, cfg.diversity)
    assert all(record.applied_penalty <= record.penalty_cap for record in adjustments)
    assert all(0 <= record.local_density <= 1 for record in adjustments)


@pytest.mark.property
def test_diversity_is_permutation_invariant(input_payload, s7_config):
    bundle, cfg = _bundle(input_payload, s7_config)
    edges, _, _ = build_similarity_graph(bundle.candidates, cfg.similarity)
    direct = adjust_diversity(bundle.candidates, edges, cfg.diversity)
    reverse = adjust_diversity(tuple(reversed(bundle.candidates)), tuple(reversed(edges)), cfg.diversity)
    assert direct == reverse


@pytest.mark.adversarial
def test_cross_group_edge_is_rejected(input_payload, s7_config):
    bundle, cfg = _bundle(input_payload, s7_config)
    bad_edge = SimilarityEdgeRecord(
        cycle_id=bundle.candidates[0].cycle_id,
        decision_time=bundle.candidates[0].decision_time,
        comparison_group_id="G1",
        candidate_id_left="A",
        candidate_id_right="E",
        similarity_score=0.9,
        stage_scores={"payoff_shape": 0.9},
        evidence_weight_coverage=1.0,
        policy_version=cfg.similarity.policy_id,
        lineage_id="bad-edge",
    )
    with pytest.raises(IntegrityViolation) as exc_info:
        adjust_diversity(bundle.candidates, (bad_edge,), cfg.diversity)
    assert exc_info.value.code == "P7_SIMILARITY_CROSS_GROUP_FORBIDDEN"
