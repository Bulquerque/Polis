from __future__ import annotations

from datetime import datetime

from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import (
    ModuleStatus,
    RecommendationState,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion.models import (
    S9ExecutionEnvelope,
)

from .enums import ReleaseState
from .hashing import sha256_hex
from .models import (
    Phase09DeliveryManifest,
    ArtifactReference,
    FeedbackDistributionManifest,
    MemoryAndP3HandoffOutput,
    ModuleDiagnostics,
    NormalizedResearchMemoryBundle,
    P0AuthorizationRequestManifest,
    P9ReleaseManifest,
    ReleaseArtifactEntry,
    ReleaseCandidateInputBundle,
    ReleaseCandidateOutput,
    SubphaseReceiptReference,
    build_module_result,
)

MODULE_ID = "P9.S10.M04"
_PROMOTION_ACTION_STATES = {
    RecommendationState.PROMOTE_RECOMMENDED,
    RecommendationState.LIMITED_CAPITAL_RECOMMENDED,
    RecommendationState.SHADOW_EXTENSION_RECOMMENDED,
    RecommendationState.CHALLENGER_ONLY,
    RecommendationState.REQUALIFICATION_REQUIRED,
    RecommendationState.ROLLBACK_RECOMMENDED,
    RecommendationState.QUARANTINE_RECOMMENDED,
}


def _artifact_entry(
    *,
    role: str,
    schema_name: str,
    payload: object,
    producer_module_id: str,
    record_count: int = 1,
    limitations: tuple[str, ...] = (),
) -> ReleaseArtifactEntry:
    return ReleaseArtifactEntry(
        artifact_role=role,
        schema_name=schema_name,
        schema_version="1.0.0",
        payload_sha256=sha256_hex(payload),
        producer_module_id=producer_module_id,
        record_count=record_count,
        limitations=limitations,
    )


def build_cycle_evaluation_release_candidate(*, inputs: ReleaseCandidateInputBundle):
    s9_payload = inputs.s9_execution_envelope.payload
    promotion_result = s9_payload.promotion_result.output
    activation_result = s9_payload.activation_gate_result.output
    invalid_receipts = tuple(
        receipt
        for receipt in inputs.upstream_subphase_receipts
        if receipt.status in {ModuleStatus.INVALID, ModuleStatus.FAILED}
    )
    reason_codes: list[str] = []
    limitations: list[str] = []

    if invalid_receipts:
        release_state = ReleaseState.RELEASE_BLOCKED_INCOMPLETE_RECEIPTS
        reason_codes.append("P9_RELEASE_UPSTREAM_RECEIPT_INVALID")
        limitations.extend(
            f"{receipt.subphase_id} status={receipt.status.value}" for receipt in invalid_receipts
        )
    elif promotion_result is None or activation_result is None:
        release_state = ReleaseState.RELEASE_BLOCKED_INCOMPLETE_RECEIPTS
        reason_codes.append("P9_RELEASE_S9_OUTPUT_INCOMPLETE")
    elif s9_payload.schema_version != "2.0.0":
        release_state = ReleaseState.RELEASE_BLOCKED_CONTRACT_DRIFT
        reason_codes.append("P9_RELEASE_S9_SCHEMA_UNSUPPORTED")
    elif promotion_result.recommendation.recommendation_state in _PROMOTION_ACTION_STATES:
        release_state = ReleaseState.RELEASE_READY_FOR_P0
    else:
        release_state = ReleaseState.RELEASE_READY_NO_PROMOTION

    if promotion_result is None:
        return build_module_result(
            module_id=MODULE_ID,
            status=ModuleStatus.INVALID,
            output=None,
            diagnostics=ModuleDiagnostics(trace=("S9 promotion output missing",)),
            reason_codes=("P9_RELEASE_S9_OUTPUT_INCOMPLETE",),
        )
    if activation_result is None:
        return build_module_result(
            module_id=MODULE_ID,
            status=ModuleStatus.INVALID,
            output=None,
            diagnostics=ModuleDiagnostics(trace=("S9 activation gate output missing",)),
            reason_codes=("P9_RELEASE_S9_OUTPUT_INCOMPLETE",),
        )

    artifacts = (
        _artifact_entry(
            role="s9_execution_envelope",
            schema_name="S9ExecutionEnvelope",
            payload=inputs.s9_execution_envelope,
            producer_module_id="P9.S9.M07",
        ),
        _artifact_entry(
            role="normalized_research_memory",
            schema_name="NormalizedResearchMemoryBundle",
            payload=inputs.normalized_memory,
            producer_module_id="P9.S10.M01",
            record_count=(
                len(inputs.normalized_memory.matured_lessons.items)
                + len(inputs.normalized_memory.research_hypotheses.items)
                + len(inputs.normalized_memory.negative_memory.items)
            ),
        ),
        _artifact_entry(
            role="system_research_memory_update",
            schema_name="SystemResearchMemoryUpdate",
            payload=inputs.memory_and_p3_output.memory_update,
            producer_module_id="P9.S10.M02",
            record_count=len(inputs.memory_and_p3_output.memory_update.memory_snapshot.items),
        ),
        _artifact_entry(
            role="p3_research_context_handoff",
            schema_name="P3ResearchContextHandoff",
            payload=inputs.memory_and_p3_output.p3_handoff,
            producer_module_id="P9.S10.M02",
            record_count=len(inputs.memory_and_p3_output.p3_handoff.context_items),
        ),
        _artifact_entry(
            role="feedback_effectiveness_report",
            schema_name="FeedbackEffectivenessReport",
            payload=inputs.feedback_effectiveness_output.report,
            producer_module_id="P9.S10.M03",
            record_count=len(inputs.feedback_effectiveness_output.report.assessments),
        ),
        _artifact_entry(
            role="feedback_lifecycle_ledger",
            schema_name="FeedbackLifecycleLedger",
            payload=inputs.feedback_effectiveness_output.lifecycle_ledger,
            producer_module_id="P9.S10.M03",
            record_count=len(inputs.feedback_effectiveness_output.lifecycle_ledger.events),
        ),
    )
    release_id = "p9-release-" + sha256_hex(
        {
            "source_cycle": inputs.source_cycle,
            "s9_sha256": inputs.s9_execution_envelope.payload_sha256,
            "memory_sha256": (
                inputs.memory_and_p3_output.memory_update.memory_snapshot.snapshot_sha256
            ),
            "effectiveness_sha256": sha256_hex(inputs.feedback_effectiveness_output),
        }
    )[:24]
    created_at = inputs.created_at
    manifest_payload = {
        "release_id": release_id,
        "source_cycle": inputs.source_cycle,
        "release_state": release_state,
        "subphase_receipts": inputs.upstream_subphase_receipts,
        "artifacts": artifacts,
        "material_limitations": tuple(limitations),
        "created_at": created_at,
    }
    release_manifest = P9ReleaseManifest(
        **manifest_payload,
        manifest_sha256=sha256_hex(manifest_payload),
    )
    p0_request = promotion_result.p0_authorization_request
    p0_manifest = P0AuthorizationRequestManifest(
        release_id=release_id,
        request_id=p0_request.request_id,
        recommendation_id=p0_request.recommendation_id,
        authorization_state=p0_request.authorization_state,
        request_payload_sha256=sha256_hex(p0_request),
    )
    manifest = activation_result.manifest
    feedback_distribution = FeedbackDistributionManifest(
        accepted_feedback_ids=tuple(package.feedback_id for package in manifest.accepted),
        rejected_feedback_ids=tuple(package.feedback_id for package in manifest.rejected),
        reserved_feedback_ids=tuple(package.feedback_id for package in manifest.reserved),
    )
    phase09_manifest = Phase09DeliveryManifest(
        module_ids=tuple(
            [*(f"P9.S9.M{index:02d}" for index in range(1, 8))]
            + [*(f"P9.S10.M{index:02d}" for index in range(1, 5))]
        ),
        source_tree_sha256=inputs.source_tree_sha256,
        s9_wheel_sha256=inputs.s9_wheel_sha256,
        s10_wheel_sha256=inputs.s10_wheel_sha256,
        consumer_receipts=inputs.consumer_receipts,
        build_environment=inputs.build_environment,
        test_summary=inputs.test_summary,
    )
    output = ReleaseCandidateOutput(
        release_state=release_state,
        release_manifest_without_s10=release_manifest,
        p0_authorization_manifest=p0_manifest,
        p3_handoff_manifest_sha256=sha256_hex(inputs.memory_and_p3_output.p3_manifest),
        feedback_distribution_manifest=feedback_distribution,
        phase09_delivery_manifest=phase09_manifest,
        reason_codes=tuple(reason_codes),
        limitations=tuple(limitations),
    )
    status = (
        ModuleStatus.SUCCESS
        if release_state
        in {ReleaseState.RELEASE_READY_FOR_P0, ReleaseState.RELEASE_READY_NO_PROMOTION}
        else ModuleStatus.INVALID
    )
    return build_module_result(
        module_id=MODULE_ID,
        status=status,
        output=output,
        diagnostics=ModuleDiagnostics(
            counters=(
                ("upstream_receipt_count", len(inputs.upstream_subphase_receipts)),
                ("consumer_receipt_count", len(inputs.consumer_receipts)),
                ("release_artifact_count", len(artifacts)),
            ),
            warnings=tuple(limitations),
            trace=(
                "release candidate created before S10 envelope sealing",
                "P0 authorization remained pending",
                "feedback activation remained prohibited",
            ),
        ),
        reason_codes=tuple(reason_codes),
    )


def build_s10_receipt_reference(
    *,
    execution_payload_sha256: str,
    cycle,
    available_at: datetime,
    run_id: str,
    status: ModuleStatus,
) -> SubphaseReceiptReference:
    schema_sha = sha256_hex({"schema": "S10ExecutionEnvelope", "version": "1.0.0"})
    ref = ArtifactReference(
        artifact_id=f"p9-s10-receipt-{execution_payload_sha256[:24]}",
        artifact_role="p9_s10_subphase_execution_receipt",
        schema_name="S10ExecutionEnvelope",
        schema_version="1.0.0",
        schema_sha256=schema_sha,
        payload_sha256=execution_payload_sha256,
        producer_module_id=MODULE_ID,
        run_id=run_id,
        cycle=cycle,
        available_at=available_at,
        location=f"memory://p9/s10/{execution_payload_sha256}",
    )
    return SubphaseReceiptReference(
        subphase_id="P9.S10",
        status=status,
        receipt_ref=ref,
        output_sha256=execution_payload_sha256,
    )
