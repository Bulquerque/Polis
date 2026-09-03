from __future__ import annotations

from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import (
    ModuleStatus,
    RecommendationState,
)
from quant_pipeline.phase_09.subphases.s10_memory_release import (
    CausalStatus,
    FeedbackLifecycleState,
    MetricDirection,
    OutcomeMaturity,
    P3ContextState,
    ResearchItemType,
    S10SubphaseState,
    run_s10_subphase,
)
from quant_pipeline.phase_09.subphases.s10_memory_release.m01_matured_research_memory import (
    normalize_matured_research_memory,
)
from quant_pipeline.phase_09.subphases.s10_memory_release.m02_research_memory_p3_handoff import (
    update_research_memory_and_build_p3_handoff,
)
from quant_pipeline.phase_09.subphases.s10_memory_release.m03_feedback_effectiveness import (
    evaluate_feedback_effectiveness,
)

from tests.s10.conftest import NOW, SOURCE_CYCLE, historical_feedback_input, valid_s10_input


def test_m01_classifies_contrary_only_rejected_and_low_confidence_unresolved() -> None:
    base = valid_s10_input().research_claim_candidates[0]
    rejected = base.model_copy(
        update={
            "candidate_id": "rejected",
            "semantic_key": "rejected-key",
            "evidence_for": (),
            "evidence_against": base.evidence_for,
            "confidence": 0.9,
            "causal_status": CausalStatus.UNKNOWN,
        }
    )
    unresolved = base.model_copy(
        update={
            "candidate_id": "unresolved",
            "semantic_key": "unresolved-key",
            "confidence": 0.1,
            "causal_status": CausalStatus.UNKNOWN,
        }
    )
    result = normalize_matured_research_memory(
        candidates=(rejected, unresolved), policy=valid_s10_input().normalization_policy
    )
    assert result.output is not None
    types = {
        item.semantic_key: item.item_type
        for item in result.output.research_hypotheses.items
    }
    assert types["rejected-key"] == ResearchItemType.REJECTED_HYPOTHESIS
    assert types["unresolved-key"] == ResearchItemType.UNRESOLVED_QUESTION


def test_m01_warns_on_unknown_relation_and_blocks_all_sensitive_flags() -> None:
    base = valid_s10_input().research_claim_candidates[0]
    candidate = base.model_copy(
        update={
            "candidate_id": "blocked",
            "semantic_key": "blocked-key",
            "supersedes_semantic_keys": ("missing-key",),
            "contains_future_outcome_identifiers": True,
            "contains_private_leaderboard_data": True,
            "contains_promoted_parameters": True,
            "contains_direct_patch_instruction": True,
            "contains_asset_specific_future_return": True,
        }
    )
    result = normalize_matured_research_memory(
        candidates=(candidate,), policy=valid_s10_input().normalization_policy
    )
    assert result.output is not None
    item = result.output.matured_lessons.items[0]
    assert len(item.export_block_reasons) == 5
    assert result.output.warnings


def test_m02_no_exportable_context_and_expiry() -> None:
    inputs = valid_s10_input()
    candidate = inputs.research_claim_candidates[0].model_copy(
        update={
            "candidate_id": "expired",
            "semantic_key": "expired-key",
            "item_type_hint": ResearchItemType.REJECTED_HYPOTHESIS,
            "expires_after_cycle": SOURCE_CYCLE,
        }
    )
    normalized = normalize_matured_research_memory(
        candidates=(candidate,), policy=inputs.normalization_policy
    ).output
    assert normalized is not None
    output = update_research_memory_and_build_p3_handoff(
        normalized=normalized,
        previous_snapshot=None,
        policy=inputs.memory_update_policy.model_copy(update={"maximum_p3_items": 0}),
        current_cycle=SOURCE_CYCLE.model_copy(update={"ordinal": SOURCE_CYCLE.ordinal + 1}),
        created_at=NOW,
    ).output
    assert output is not None
    assert output.p3_handoff.state == P3ContextState.NO_EXPORTABLE_CONTEXT
    assert any(item.state.value == "EXPIRED" for item in output.memory_update.memory_snapshot.items)


def test_m03_reverted_unknown_metric_and_missing_outcome_states() -> None:
    inputs = historical_feedback_input()
    first, second = inputs.activations
    reverted = first.model_copy(update={"reverted": True})
    unknown = second.model_copy(update={"target_metric_id": "unknown-metric"})
    result = evaluate_feedback_effectiveness(
        inputs=inputs.model_copy(
            update={
                "activations": (reverted, unknown),
                "outcome_pairs": (),
            }
        ),
        evaluated_at=NOW,
    )
    assert result.output is not None
    states = {item.feedback_id: item.state for item in result.output.report.assessments}
    assert states[first.feedback_id] == FeedbackLifecycleState.REVERTED
    assert states[second.feedback_id] == FeedbackLifecycleState.INCONCLUSIVE


def test_m03_minimize_direction_and_small_sample_are_inconclusive() -> None:
    inputs = historical_feedback_input()
    metric = inputs.evaluation_policy.metrics[0].model_copy(
        update={"direction": MetricDirection.MINIMIZE, "minimum_observations": 20}
    )
    result = evaluate_feedback_effectiveness(
        inputs=inputs.model_copy(
            update={
                "evaluation_policy": inputs.evaluation_policy.model_copy(
                    update={"metrics": (metric,)}
                )
            }
        ),
        evaluated_at=NOW,
    )
    assert result.output is not None
    assert all(
        item.state == FeedbackLifecycleState.INCONCLUSIVE
        for item in result.output.report.assessments
    )


def test_service_emits_ready_no_promotion_state() -> None:
    inputs = valid_s10_input()
    s9_payload = inputs.s9_execution_envelope.payload
    promotion = s9_payload.promotion_result.output
    assert promotion is not None
    altered_recommendation = promotion.recommendation.model_copy(
        update={"recommendation_state": RecommendationState.RETAIN_CHAMPION}
    )
    altered_promotion = promotion.model_copy(update={"recommendation": altered_recommendation})
    altered_result = s9_payload.promotion_result.model_copy(update={"output": altered_promotion})
    altered_payload = s9_payload.model_copy(update={"promotion_result": altered_result})
    altered_envelope = type(inputs.s9_execution_envelope)(
        payload=altered_payload,
        payload_sha256=__import__(
            "quant_pipeline.phase_09.subphases.s10_memory_release.hashing",
            fromlist=["sha256_hex"],
        ).sha256_hex(altered_payload),
    )
    result = run_s10_subphase(
        inputs=inputs.model_copy(update={"s9_execution_envelope": altered_envelope})
    )
    assert result.execution_envelope.payload.subphase_state == (
        S10SubphaseState.P9_RELEASE_READY_NO_PROMOTION
    )


def test_service_invalid_when_upstream_receipt_invalid() -> None:
    inputs = valid_s10_input()
    first = inputs.upstream_subphase_receipts[0].model_copy(
        update={"status": ModuleStatus.INVALID}
    )
    result = run_s10_subphase(
        inputs=inputs.model_copy(
            update={
                "upstream_subphase_receipts": (
                    first,
                    *inputs.upstream_subphase_receipts[1:],
                )
            }
        )
    )
    assert result.execution_envelope.payload.subphase_state == S10SubphaseState.P9_RELEASE_INVALID
    assert result.publication_manifest is not None


def test_m03_pending_pair_branch() -> None:
    inputs = historical_feedback_input()
    pairs = tuple(
        pair.model_copy(update={"maturity": OutcomeMaturity.NOT_MATURED})
        for pair in inputs.outcome_pairs
    )
    result = evaluate_feedback_effectiveness(
        inputs=inputs.model_copy(update={"outcome_pairs": pairs}), evaluated_at=NOW
    )
    assert result.output is not None
    assert result.output.report.pending_count == len(inputs.feedback_packages)
