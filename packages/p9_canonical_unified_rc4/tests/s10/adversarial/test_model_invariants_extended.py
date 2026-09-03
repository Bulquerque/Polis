from __future__ import annotations

from math import inf

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import ModuleStatus
from quant_pipeline.phase_09.subphases.s10_memory_release import (
    FeedbackLifecycleState,
    MetricDirection,
    P3ContextState,
)
from quant_pipeline.phase_09.subphases.s10_memory_release.hashing import sha256_hex
from quant_pipeline.phase_09.subphases.s10_memory_release.m01_matured_research_memory import (
    normalize_matured_research_memory,
)
from quant_pipeline.phase_09.subphases.s10_memory_release.m02_research_memory_p3_handoff import (
    update_research_memory_and_build_p3_handoff,
)
from quant_pipeline.phase_09.subphases.s10_memory_release.m03_feedback_effectiveness import (
    evaluate_feedback_effectiveness,
)
from quant_pipeline.phase_09.subphases.s10_memory_release.models import (
    FeedbackEffectivenessAssessment,
    FeedbackEffectivenessReport,
    FeedbackEvaluationPolicy,
    FeedbackLifecycleLedger,
    FeedbackOutcomePair,
    MetricEvaluationPolicy,
    ModuleDiagnostics,
    ModuleResult,
    NormalizedResearchMemoryBundle,
    P3ResearchContextHandoff,
    ResearchClaimCandidate,
    ResearchMemoryItem,
    ResearchNormalizationPolicy,
)

from tests.s10.conftest import NOW, historical_feedback_input, valid_s10_input


def _normalized():
    inputs = valid_s10_input()
    output = normalize_matured_research_memory(
        candidates=inputs.research_claim_candidates,
        policy=inputs.normalization_policy,
    ).output
    assert output is not None
    return output


def _effectiveness_output():
    output = evaluate_feedback_effectiveness(
        inputs=historical_feedback_input(), evaluated_at=NOW
    ).output
    assert output is not None
    return output


def test_module_result_rejects_success_without_output() -> None:
    with pytest.raises(ValidationError):
        ModuleResult[dict](
            module_id="P9.S10.M01",
            status=ModuleStatus.SUCCESS,
            output=None,
            diagnostics=ModuleDiagnostics(),
        )


def test_module_result_rejects_invalid_without_reason() -> None:
    with pytest.raises(ValidationError):
        ModuleResult[dict](
            module_id="P9.S10.M01",
            status=ModuleStatus.INVALID,
            output=None,
            diagnostics=ModuleDiagnostics(),
        )


def test_module_result_rejects_output_hash_mismatch() -> None:
    with pytest.raises(ValidationError):
        ModuleResult[dict](
            module_id="P9.S10.M01",
            status=ModuleStatus.SUCCESS,
            output={"x": 1},
            diagnostics=ModuleDiagnostics(),
            output_sha256="0" * 64,
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"evidence_for": (), "evidence_against": ()},
        {"source_cycles": ()},
        {"expires_after_cycle": {"cycle_id": "old", "ordinal": 0}},
    ],
)
def test_research_candidate_cross_field_invariants(updates) -> None:
    candidate = valid_s10_input().research_claim_candidates[0]
    payload = candidate.model_dump(mode="python")
    payload.update(updates)
    with pytest.raises(ValidationError):
        ResearchClaimCandidate.model_validate(payload)


def test_research_candidate_cannot_reference_its_own_semantic_key() -> None:
    candidate = valid_s10_input().research_claim_candidates[0]
    for field in ("supersedes_semantic_keys", "contradicts_semantic_keys"):
        payload = candidate.model_dump(mode="python")
        payload[field] = (candidate.semantic_key,)
        with pytest.raises(ValidationError):
            ResearchClaimCandidate.model_validate(payload)


def test_research_normalization_policy_rejects_inverted_thresholds() -> None:
    with pytest.raises(ValidationError):
        ResearchNormalizationPolicy(
            policy_id="bad",
            supported_lesson_confidence=0.5,
            conditional_lesson_confidence=0.8,
        )
    with pytest.raises(ValidationError):
        ResearchNormalizationPolicy(
            policy_id="bad",
            conditional_lesson_confidence=0.5,
            plausible_hypothesis_confidence=0.8,
        )


def test_memory_item_requires_evidence_and_block_reason() -> None:
    item = _normalized().matured_lessons.items[0]
    payload = item.model_dump(mode="python")
    payload.update({"evidence_for": (), "evidence_against": ()})
    with pytest.raises(ValidationError):
        ResearchMemoryItem.model_validate(payload)
    payload = item.model_dump(mode="python")
    payload.update({"export_blocked": True, "export_block_reasons": ()})
    with pytest.raises(ValidationError):
        ResearchMemoryItem.model_validate(payload)
    payload = item.model_dump(mode="python")
    payload.update({"supersedes_item_ids": (item.item_id,)})
    with pytest.raises(ValidationError):
        ResearchMemoryItem.model_validate(payload)


def test_normalized_bundle_rejects_duplicate_item_id() -> None:
    normalized = _normalized()
    item = normalized.matured_lessons.items[0]
    payload = normalized.model_dump(mode="python")
    payload["research_hypotheses"]["items"] = (item,)
    with pytest.raises(ValidationError):
        NormalizedResearchMemoryBundle.model_validate(payload)


def test_p3_ready_state_requires_context_item() -> None:
    with pytest.raises(ValidationError):
        P3ResearchContextHandoff(
            state=P3ContextState.P3_CONTEXT_READY,
            context_items=(),
        )


def test_feedback_policy_rejects_duplicate_metric() -> None:
    metric = MetricEvaluationPolicy(
        metric_id="alpha", direction=MetricDirection.MAXIMIZE, minimum_material_effect=0.01
    )
    with pytest.raises(ValidationError):
        FeedbackEvaluationPolicy(policy_id="dup", metrics=(metric, metric))


def test_feedback_outcome_rejects_nonfinite_values() -> None:
    pair = historical_feedback_input().outcome_pairs[0]
    payload = pair.model_dump(mode="python")
    payload["intervention_value"] = inf
    with pytest.raises(ValidationError):
        FeedbackOutcomePair.model_validate(payload)


def test_feedback_assessment_requires_complete_ordered_interval_and_metric() -> None:
    with pytest.raises(ValidationError):
        FeedbackEffectivenessAssessment(
            feedback_id="fb",
            state=FeedbackLifecycleState.EFFECTIVE,
            sample_size=5,
            confidence_lower=0.1,
        )
    with pytest.raises(ValidationError):
        FeedbackEffectivenessAssessment(
            feedback_id="fb",
            state=FeedbackLifecycleState.EFFECTIVE,
            metric_id="alpha",
            sample_size=5,
            confidence_lower=0.2,
            confidence_upper=0.1,
        )
    with pytest.raises(ValidationError):
        FeedbackEffectivenessAssessment(
            feedback_id="fb",
            state=FeedbackLifecycleState.EFFECTIVE,
            sample_size=5,
        )


def test_feedback_report_rejects_count_mismatch() -> None:
    report = _effectiveness_output().report
    payload = report.model_dump(mode="python")
    payload["effective_count"] += 1
    with pytest.raises(ValidationError):
        FeedbackEffectivenessReport.model_validate(payload)


def test_feedback_ledger_rejects_duplicate_and_hash_mismatch() -> None:
    ledger = _effectiveness_output().lifecycle_ledger
    payload = ledger.model_dump(mode="python")
    payload["events"] = ledger.events + (ledger.events[0],)
    payload["ledger_sha256"] = sha256_hex(
        {
            "previous_ledger_sha256": ledger.previous_ledger_sha256,
            "events": payload["events"],
        }
    )
    with pytest.raises(ValidationError):
        FeedbackLifecycleLedger.model_validate(payload)
    payload = ledger.model_dump(mode="python")
    payload["ledger_sha256"] = "0" * 64
    with pytest.raises(ValidationError):
        FeedbackLifecycleLedger.model_validate(payload)
