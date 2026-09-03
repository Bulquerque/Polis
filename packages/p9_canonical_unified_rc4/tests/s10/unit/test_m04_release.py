from __future__ import annotations

from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import ModuleStatus
from quant_pipeline.phase_09.subphases.s10_memory_release import ReleaseState
from quant_pipeline.phase_09.subphases.s10_memory_release.m01_matured_research_memory import (
    normalize_matured_research_memory,
)
from quant_pipeline.phase_09.subphases.s10_memory_release.m02_research_memory_p3_handoff import (
    update_research_memory_and_build_p3_handoff,
)
from quant_pipeline.phase_09.subphases.s10_memory_release.m03_feedback_effectiveness import (
    evaluate_feedback_effectiveness,
)
from quant_pipeline.phase_09.subphases.s10_memory_release.m04_cycle_release import (
    build_cycle_evaluation_release_candidate,
)
from quant_pipeline.phase_09.subphases.s10_memory_release.models import ReleaseCandidateInputBundle

from tests.s10.conftest import NOW, historical_feedback_input, valid_s10_input


def candidate_input():
    inputs = valid_s10_input()
    normalized = normalize_matured_research_memory(
        candidates=inputs.research_claim_candidates,
        policy=inputs.normalization_policy,
    ).output
    assert normalized is not None
    memory = update_research_memory_and_build_p3_handoff(
        normalized=normalized,
        previous_snapshot=inputs.previous_memory_snapshot,
        policy=inputs.memory_update_policy,
        current_cycle=inputs.source_cycle,
        created_at=NOW,
    ).output
    assert memory is not None
    effectiveness = evaluate_feedback_effectiveness(
        inputs=historical_feedback_input(), evaluated_at=NOW
    ).output
    assert effectiveness is not None
    return ReleaseCandidateInputBundle(
        s9_execution_envelope=inputs.s9_execution_envelope,
        source_cycle=inputs.source_cycle,
        normalized_memory=normalized,
        memory_and_p3_output=memory,
        feedback_effectiveness_output=effectiveness,
        upstream_subphase_receipts=inputs.upstream_subphase_receipts,
        consumer_receipts=inputs.consumer_receipts,
        build_environment=inputs.build_environment,
        test_summary=inputs.test_summary,
        source_tree_sha256=inputs.source_tree_sha256,
        s9_wheel_sha256=inputs.s9_wheel_sha256,
        s10_wheel_sha256=inputs.s10_wheel_sha256,
        test_report_ref=inputs.test_report_ref,
        source_tree_ref=inputs.source_tree_ref,
        s9_wheel_ref=inputs.s9_wheel_ref,
        s10_wheel_ref=inputs.s10_wheel_ref,
        created_at=NOW,
    )


def test_release_ready_for_p0() -> None:
    result = build_cycle_evaluation_release_candidate(inputs=candidate_input())
    assert result.output is not None
    assert result.output.release_state == ReleaseState.RELEASE_READY_FOR_P0
    assert result.output.p0_authorization_manifest.authorization_state.value == "PENDING_P0"
    assert not result.output.feedback_distribution_manifest.activated_feedback_ids


def test_invalid_upstream_receipt_blocks_release() -> None:
    inputs = candidate_input()
    first = inputs.upstream_subphase_receipts[0].model_copy(
        update={"status": ModuleStatus.INVALID}
    )
    result = build_cycle_evaluation_release_candidate(
        inputs=inputs.model_copy(
            update={
                "upstream_subphase_receipts": (
                    first,
                    *inputs.upstream_subphase_receipts[1:],
                )
            }
        )
    )
    assert result.output is not None
    assert result.status == ModuleStatus.INVALID
    assert result.output.release_state == ReleaseState.RELEASE_BLOCKED_INCOMPLETE_RECEIPTS


def test_release_manifest_references_nine_upstream_subphases() -> None:
    result = build_cycle_evaluation_release_candidate(inputs=candidate_input())
    assert result.output is not None
    ids = {
        receipt.subphase_id
        for receipt in result.output.release_manifest_without_s10.subphase_receipts
    }
    assert ids == {f"P9.S{index}" for index in range(1, 10)}


def test_phase09_manifest_covers_eleven_modules() -> None:
    result = build_cycle_evaluation_release_candidate(inputs=candidate_input())
    assert result.output is not None
    assert len(result.output.phase09_delivery_manifest.module_ids) == 11
