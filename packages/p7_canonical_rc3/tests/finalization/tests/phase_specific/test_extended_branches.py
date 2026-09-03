from __future__ import annotations

from dataclasses import replace
from math import nan
from pathlib import Path

import pytest

from quant_pipeline.phase_07_strategy_tournament.finalization.application.module_io import parse_envelope, parse_records
from quant_pipeline.phase_07_strategy_tournament.finalization.application.reconciliation import load_scoring_bundle
from quant_pipeline.phase_07_strategy_tournament.finalization.artifacts import ArtifactEnvelope, build_artifact, canonical_json_bytes
from quant_pipeline.phase_07_strategy_tournament.finalization.boundary.config import S7Config
from quant_pipeline.phase_07_strategy_tournament.finalization.boundary.outputs import (
    BlockedRecord,
    DiversityAdjustedScoreRecord,
    SimilarityEdgeRecord,
)
from quant_pipeline.phase_07_strategy_tournament.finalization.config_loader import _load_mapping, load_s7_config
from quant_pipeline.phase_07_strategy_tournament.finalization.errors import ContractViolation, InternalInvariantViolation
from quant_pipeline.phase_07_strategy_tournament.finalization.subphases.s7_safety_diversity.abstention import (
    apply_group_coverage,
    candidate_abstention_reasons,
)
from quant_pipeline.phase_07_strategy_tournament.finalization.subphases.s7_safety_diversity.diversity import adjust_diversity
from quant_pipeline.phase_07_strategy_tournament.finalization.subphases.s7_safety_diversity.rankability import build_rankability
from quant_pipeline.phase_07_strategy_tournament.finalization.subphases.s7_safety_diversity.safety import evaluate_safety
from quant_pipeline.phase_07_strategy_tournament.finalization.subphases.s7_safety_diversity.similarity import _cosine, _pearson

ROOT = Path(__file__).resolve().parents[2]


def _candidate_map(input_payload, s7_config):
    cfg = S7Config.model_validate(s7_config)
    bundle = load_scoring_bundle(input_payload, "TEST", cfg.forbidden_fields)
    return {candidate.candidate_id: candidate for candidate in bundle.candidates}, cfg


@pytest.mark.unit
@pytest.mark.parametrize(
    ("update", "expected_code"),
    [
        ({"context_available": False}, "P7_MISSING_STRATEGY_CONTEXT"),
        ({"model_promotion_status": "SHADOW"}, "P7_MODEL_NOT_PROMOTED"),
        ({"model_compatibility_status": "INCOMPATIBLE"}, "P7_MODEL_INCOMPATIBLE"),
    ],
)
def test_safety_individual_material_rules(input_payload, s7_config, update, expected_code):
    candidates, cfg = _candidate_map(input_payload, s7_config)
    outcome = evaluate_safety(replace(candidates["A"], **update), 0.5, cfg.safety, ())
    assert expected_code in outcome.reason_codes


@pytest.mark.unit
def test_safety_rejects_missing_and_nonfinite_score(input_payload, s7_config):
    candidates, cfg = _candidate_map(input_payload, s7_config)
    assert "P7_NON_FINITE_SCORE" in evaluate_safety(candidates["A"], None, cfg.safety, ()).reason_codes
    assert "P7_NON_FINITE_SCORE" in evaluate_safety(candidates["A"], nan, cfg.safety, ()).reason_codes


@pytest.mark.unit
def test_safety_rejects_future_execution_context(input_payload, s7_config):
    candidates, cfg = _candidate_map(input_payload, s7_config)
    future = replace(candidates["A"], execution_context_time=candidates["A"].decision_time.replace(year=2027))
    assert "P7_STALE_EXECUTION_CONTEXT" in evaluate_safety(future, 0.5, cfg.safety, ()).reason_codes


@pytest.mark.unit
def test_abstention_covers_interval_disagreement_and_calibration(input_payload, s7_config):
    candidates, cfg = _candidate_map(input_payload, s7_config)
    candidate = replace(
        candidates["A"],
        interval_lower=-1.0,
        interval_upper=1.0,
        model_disagreement=0.9,
        calibration_status="FAILED",
    )
    reasons = candidate_abstention_reasons(candidate, cfg.abstention)
    assert set(reasons) >= {
        "P7_SCORE_UNCERTAINTY_TOO_WIDE",
        "P7_MODEL_DISAGREEMENT_HIGH",
        "P7_CALIBRATION_INSUFFICIENT",
    }


@pytest.mark.unit
def test_group_coverage_marks_only_provisional_candidates(input_payload, s7_config):
    candidates, cfg = _candidate_map(input_payload, s7_config)
    members = (candidates["A"], candidates["B"], candidates["C"])
    reasons = {"A": (), "B": ("P7_CONFIDENCE_BELOW_MINIMUM",), "C": ("P7_MODERATE_OOD_ABSTAIN",)}
    strict = cfg.abstention.model_copy(update={"minimum_group_rankable_count": 2})
    updated, group = apply_group_coverage(reasons, members, frozenset(), strict)
    assert updated["A"] == ("P7_GROUP_COVERAGE_INSUFFICIENT",)
    assert "P7_GROUP_COVERAGE_INSUFFICIENT" in group["G1"]


@pytest.mark.unit
def test_group_reports_all_low_confidence(input_payload, s7_config):
    candidates, cfg = _candidate_map(input_payload, s7_config)
    members = (candidates["E"], candidates["F"])
    reasons = {candidate.candidate_id: ("P7_CONFIDENCE_BELOW_MINIMUM",) for candidate in members}
    _, group = apply_group_coverage(reasons, members, frozenset(), cfg.abstention)
    assert set(group["G2"]) == {"P7_ALL_CANDIDATES_LOW_CONFIDENCE", "P7_NO_RANKABLE_CANDIDATES"}


@pytest.mark.unit
def test_rankability_partition_invariants(input_payload, s7_config):
    candidates, cfg = _candidate_map(input_payload, s7_config)
    adjusted = {
        candidate_id: DiversityAdjustedScoreRecord(
            cycle_id=candidate.cycle_id,
            decision_time=candidate.decision_time,
            comparison_group_id=candidate.comparison_group_id,
            candidate_id=candidate_id,
            hybrid_score=candidate.hybrid_score,
            diversity_penalty=0.0,
            diversity_adjusted_score=candidate.hybrid_score,
            score_confidence=candidate.score_confidence,
            score_status="VALID",
            policy_version="test",
            lineage_id=candidate.lineage_id,
        )
        for candidate_id, candidate in candidates.items()
    }
    blocked = BlockedRecord(
        cycle_id=candidates["D"].cycle_id,
        decision_time=candidates["D"].decision_time,
        comparison_group_id="G1",
        candidate_id="D",
        reason_codes=("P7_UPSTREAM_DEFINED_RISK_INVALID",),
        evidence_ids=("risk",),
        policy_version="test",
        lineage_id=candidates["D"].lineage_id,
    )
    with pytest.raises(InternalInvariantViolation) as overlap:
        build_rankability(tuple(candidates.values()), set(candidates), {"D": blocked}, adjusted, cfg.abstention, "lineage")
    assert overlap.value.code == "P7_TERMINAL_STATE_OVERLAP"
    with pytest.raises(InternalInvariantViolation) as missing:
        build_rankability(tuple(candidates.values()), {"A"}, {}, adjusted, cfg.abstention, "lineage")
    assert missing.value.code == "P7_CANDIDATE_CONSERVATION_FAILED"


@pytest.mark.unit
def test_rankable_score_must_exist(input_payload, s7_config):
    candidates, cfg = _candidate_map(input_payload, s7_config)
    candidate = candidates["A"]
    adjusted = {
        "A": DiversityAdjustedScoreRecord(
            cycle_id=candidate.cycle_id,
            decision_time=candidate.decision_time,
            comparison_group_id=candidate.comparison_group_id,
            candidate_id="A",
            hybrid_score=candidate.hybrid_score,
            diversity_penalty=0.0,
            diversity_adjusted_score=None,
            score_confidence=candidate.score_confidence,
            score_status="MISSING",
            policy_version="test",
            lineage_id=candidate.lineage_id,
        )
    }
    with pytest.raises(InternalInvariantViolation) as exc_info:
        build_rankability((candidate,), {"A"}, {}, adjusted, cfg.abstention, "lineage")
    assert exc_info.value.code == "P7_RANKABLE_SCORE_MISSING"


@pytest.mark.unit
def test_similarity_numeric_edge_cases():
    assert _cosine((), ()) is None
    assert _cosine((0.0, 0.0), (0.0, 0.0)) == 1.0
    assert _cosine((0.0, 0.0), (1.0, 0.0)) is None
    assert _cosine((1.0,), (1.0, 2.0)) is None
    assert _pearson((1.0,), (1.0,)) is None


@pytest.mark.adversarial
def test_duplicate_similarity_edge_is_rejected(input_payload, s7_config):
    candidates, cfg = _candidate_map(input_payload, s7_config)
    base = candidates["A"]
    edge = SimilarityEdgeRecord(
        cycle_id=base.cycle_id,
        decision_time=base.decision_time,
        comparison_group_id="G1",
        candidate_id_left="A",
        candidate_id_right="B",
        similarity_score=0.9,
        stage_scores={"payoff_shape": 0.9},
        evidence_weight_coverage=1.0,
        policy_version="test",
        lineage_id="edge",
    )
    from quant_pipeline.phase_07_strategy_tournament.finalization.errors import IntegrityViolation

    with pytest.raises(IntegrityViolation):
        adjust_diversity(tuple(candidates.values()), (edge, edge), cfg.diversity)


@pytest.mark.contract
def test_config_loader_reads_versioned_policy_files(s7_config):
    config = load_s7_config(ROOT / "policies", s7_config["runtime"])
    assert config.similarity.policy_id == "p7_similarity_v1"
    assert config.safety.policy_id == "p7_safety_v1"


@pytest.mark.contract
def test_config_loader_rejects_non_mapping_yaml(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(ValueError):
        _load_mapping(path)


@pytest.mark.contract
def test_module_io_reports_missing_and_bad_record(input_payload):
    with pytest.raises(ContractViolation) as missing:
        parse_envelope({}, "missing", "TEST")
    assert missing.value.code == "P7_INPUT_ARTIFACT_MISSING"
    envelope = ArtifactEnvelope.model_validate(input_payload["hybrid_candidate_score_panel"])
    with pytest.raises(ContractViolation) as bad:
        parse_records(envelope, SimilarityEdgeRecord, "TEST")
    assert bad.value.code == "P7_RECORD_SCHEMA_INVALID"


@pytest.mark.unit
def test_canonical_serialization_marks_nonfinite_values():
    assert b"__non_finite__" in canonical_json_bytes({"value": float("inf")})
