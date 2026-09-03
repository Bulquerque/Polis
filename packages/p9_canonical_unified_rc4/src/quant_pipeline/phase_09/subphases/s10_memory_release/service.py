from __future__ import annotations

from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import ModuleStatus

from .enums import ReleaseState, S10SubphaseState
from .hashing import sha256_hex
from .m01_matured_research_memory import normalize_matured_research_memory
from .m02_research_memory_p3_handoff import update_research_memory_and_build_p3_handoff
from .m03_feedback_effectiveness import evaluate_feedback_effectiveness
from .m04_cycle_release import (
    build_cycle_evaluation_release_candidate,
    build_s10_receipt_reference,
)
from .models import (
    ModuleDiagnostics,
    P9ReleasePublicationManifest,
    ReleaseCandidateInputBundle,
    S10ExecutionBundle,
    S10ExecutionEnvelope,
    S10InputBundle,
    S10SubphaseDelivery,
    build_module_result,
)


def _invalid_result(module_id: str, reason_code: str, trace: str):
    return build_module_result(
        module_id=module_id,
        status=ModuleStatus.INVALID,
        output=None,
        diagnostics=ModuleDiagnostics(trace=(trace,)),
        reason_codes=(reason_code,),
    )


def run_s10_subphase(*, inputs: S10InputBundle) -> S10SubphaseDelivery:
    normalization_result = normalize_matured_research_memory(
        candidates=inputs.research_claim_candidates,
        policy=inputs.normalization_policy,
    )
    effectiveness_result = evaluate_feedback_effectiveness(
        inputs=inputs.feedback_effectiveness_input,
        evaluated_at=inputs.created_at,
    )

    if normalization_result.output is None:
        memory_handoff_result = _invalid_result(
            "P9.S10.M02",
            "P9_MEMORY_NORMALIZATION_REQUIRED",
            "M02 could not execute because M01 produced no normalized memory",
        )
    else:
        memory_handoff_result = update_research_memory_and_build_p3_handoff(
            normalized=normalization_result.output,
            previous_snapshot=inputs.previous_memory_snapshot,
            policy=inputs.memory_update_policy,
            current_cycle=inputs.source_cycle,
            created_at=inputs.created_at,
        )

    if (
        normalization_result.output is None
        or memory_handoff_result.output is None
        or effectiveness_result.output is None
    ):
        release_candidate_result = _invalid_result(
            "P9.S10.M04",
            "P9_RELEASE_REQUIRED_OUTPUT_MISSING",
            "M04 could not execute because an upstream S10 module has no output",
        )
    else:
        release_input = ReleaseCandidateInputBundle(
            s9_execution_envelope=inputs.s9_execution_envelope,
            source_cycle=inputs.source_cycle,
            normalized_memory=normalization_result.output,
            memory_and_p3_output=memory_handoff_result.output,
            feedback_effectiveness_output=effectiveness_result.output,
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
            created_at=inputs.created_at,
        )
        release_candidate_result = build_cycle_evaluation_release_candidate(inputs=release_input)

    statuses = {
        normalization_result.status,
        memory_handoff_result.status,
        effectiveness_result.status,
        release_candidate_result.status,
    }
    release_output = release_candidate_result.output
    if ModuleStatus.INVALID in statuses or ModuleStatus.FAILED in statuses:
        subphase_state = S10SubphaseState.P9_RELEASE_INVALID
    elif release_output is None:
        subphase_state = S10SubphaseState.P9_RELEASE_PENDING_EVIDENCE
    elif release_output.release_state == ReleaseState.RELEASE_READY_FOR_P0:
        subphase_state = S10SubphaseState.P9_RELEASE_READY
    elif release_output.release_state == ReleaseState.RELEASE_READY_NO_PROMOTION:
        subphase_state = S10SubphaseState.P9_RELEASE_READY_NO_PROMOTION
    else:
        subphase_state = S10SubphaseState.P9_RELEASE_PENDING_EVIDENCE

    bundle = S10ExecutionBundle(
        normalization_result=normalization_result,
        memory_handoff_result=memory_handoff_result,
        effectiveness_result=effectiveness_result,
        release_candidate_result=release_candidate_result,
        subphase_state=subphase_state,
        created_at=inputs.created_at,
    )
    envelope = S10ExecutionEnvelope(payload=bundle, payload_sha256=sha256_hex(bundle))
    publication = None
    if release_output is not None:
        receipt_status = {
            S10SubphaseState.P9_RELEASE_READY: ModuleStatus.SUCCESS,
            S10SubphaseState.P9_RELEASE_READY_NO_PROMOTION: ModuleStatus.SUCCESS,
            S10SubphaseState.P9_RELEASE_PENDING_EVIDENCE: ModuleStatus.LIMITED,
            S10SubphaseState.P9_RELEASE_INVALID: ModuleStatus.INVALID,
        }[subphase_state]
        first_receipt = inputs.upstream_subphase_receipts[0]
        s10_receipt = build_s10_receipt_reference(
            execution_payload_sha256=envelope.payload_sha256,
            cycle=inputs.source_cycle,
            available_at=inputs.created_at,
            run_id=first_receipt.receipt_ref.run_id,
            status=receipt_status,
        )
        all_receipts = tuple(
            sorted(
                inputs.upstream_subphase_receipts + (s10_receipt,),
                key=lambda receipt: receipt.subphase_id,
            )
        )
        publication_payload = {
            "release_id": release_output.release_manifest_without_s10.release_id,
            "all_subphase_receipts": all_receipts,
            "s10_execution_sha256": envelope.payload_sha256,
            "candidate_release_manifest_sha256": (
                release_output.release_manifest_without_s10.manifest_sha256
            ),
        }
        publication = P9ReleasePublicationManifest(
            **publication_payload,
            publication_sha256=sha256_hex(publication_payload),
        )
    delivery_payload = {
        "execution_envelope": envelope,
        "publication_manifest": publication,
    }
    return S10SubphaseDelivery(
        execution_envelope=envelope,
        publication_manifest=publication,
        delivery_sha256=sha256_hex(delivery_payload),
    )
