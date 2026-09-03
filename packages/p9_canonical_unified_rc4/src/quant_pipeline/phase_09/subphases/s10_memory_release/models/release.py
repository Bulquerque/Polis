from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints, field_validator, model_validator

from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import (
    ModuleStatus,
    P0AuthorizationState,
    RecommendationState,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion.models import (
    FeedbackActivationGateOutput,
    PromotionModuleOutput,
    S9ExecutionEnvelope,
)

from ..enums import ReleaseState, S10SubphaseState
from ..hashing import sha256_hex
from .common import (
    ArtifactReference,
    CycleRef,
    LongText,
    ModuleResult,
    NonEmptyStr,
    ReasonCode,
    Sha256Hex,
    StrictModel,
    UtcTimestampedModel,
)
from .effectiveness import FeedbackEffectivenessModuleOutput
from .memory import MemoryAndP3HandoffOutput, NormalizedResearchMemoryBundle

SubphaseId = Annotated[str, StringConstraints(pattern=r"^P9\.S(?:[1-9]|10)$")]


class SubphaseReceiptReference(StrictModel):
    subphase_id: SubphaseId
    status: ModuleStatus
    receipt_ref: ArtifactReference
    output_sha256: Sha256Hex
    limitations: tuple[LongText, ...] = ()

    @model_validator(mode="after")
    def validate_receipt(self) -> "SubphaseReceiptReference":
        if self.receipt_ref.payload_sha256 != self.output_sha256:
            raise ValueError("subphase receipt output hash mismatch")
        return self


class ConsumerReceiptReference(StrictModel):
    consumer_id: NonEmptyStr
    source_contract_name: NonEmptyStr
    source_contract_version: NonEmptyStr
    receipt_ref: ArtifactReference
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    reserved_count: int = Field(ge=0)


class BuildEnvironment(StrictModel):
    python_version: NonEmptyStr
    platform: NonEmptyStr
    pydantic_version: NonEmptyStr
    s9_distribution_version: NonEmptyStr
    s10_distribution_version: NonEmptyStr
    dependency_lock_sha256: Sha256Hex


class TestSummary(StrictModel):
    total: int = Field(gt=0)
    passed: int = Field(gt=0)
    failed: int = Field(ge=0)
    line_coverage_percent: float = Field(ge=0.0, le=100.0)
    branch_coverage_percent: float = Field(ge=0.0, le=100.0)
    report_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_counts(self) -> "TestSummary":
        if self.passed + self.failed != self.total:
            raise ValueError("test counts must reconcile")
        if self.failed:
            raise ValueError("release test evidence must contain zero failures")
        if self.line_coverage_percent < 80.0 or self.branch_coverage_percent < 70.0:
            raise ValueError("release coverage gates require 80% lines and 70% branches")
        return self


class ReleaseArtifactEntry(StrictModel):
    artifact_role: NonEmptyStr
    schema_name: NonEmptyStr
    schema_version: NonEmptyStr
    payload_sha256: Sha256Hex
    producer_module_id: NonEmptyStr
    record_count: int = Field(ge=0)
    limitations: tuple[LongText, ...] = ()


class P9ReleaseManifest(UtcTimestampedModel):
    release_id: NonEmptyStr
    source_cycle: CycleRef
    release_state: ReleaseState
    subphase_receipts: tuple[SubphaseReceiptReference, ...]
    artifacts: tuple[ReleaseArtifactEntry, ...]
    material_limitations: tuple[LongText, ...] = ()
    created_at: datetime
    manifest_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_manifest(self) -> "P9ReleaseManifest":
        subphase_ids = [receipt.subphase_id for receipt in self.subphase_receipts]
        if len(subphase_ids) != len(set(subphase_ids)):
            raise ValueError("release subphase receipts must be unique")
        payload = {
            "release_id": self.release_id,
            "source_cycle": self.source_cycle,
            "release_state": self.release_state,
            "subphase_receipts": self.subphase_receipts,
            "artifacts": self.artifacts,
            "material_limitations": self.material_limitations,
            "created_at": self.created_at,
        }
        if self.manifest_sha256 != sha256_hex(payload):
            raise ValueError("P9 release manifest hash mismatch")
        return self


class P0AuthorizationRequestManifest(StrictModel):
    release_id: NonEmptyStr
    request_id: NonEmptyStr
    recommendation_id: NonEmptyStr
    authorization_state: P0AuthorizationState
    request_payload_sha256: Sha256Hex

    @model_validator(mode="after")
    def preserve_p0_boundary(self) -> "P0AuthorizationRequestManifest":
        if self.authorization_state != P0AuthorizationState.PENDING_P0:
            raise ValueError("P9 release can only carry pending P0 authorization")
        return self


class FeedbackDistributionManifest(StrictModel):
    accepted_feedback_ids: tuple[NonEmptyStr, ...]
    rejected_feedback_ids: tuple[NonEmptyStr, ...]
    reserved_feedback_ids: tuple[NonEmptyStr, ...]
    activated_feedback_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def prevent_activation(self) -> "FeedbackDistributionManifest":
        if self.activated_feedback_ids:
            raise ValueError("P9 release cannot activate feedback")
        sets = [
            set(self.accepted_feedback_ids),
            set(self.rejected_feedback_ids),
            set(self.reserved_feedback_ids),
        ]
        if sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]:
            raise ValueError("feedback distribution sets must be disjoint")
        return self


class Phase09DeliveryManifest(StrictModel):
    producer_id: NonEmptyStr = "PHASE09_RELEASE"
    module_ids: tuple[NonEmptyStr, ...]
    source_tree_sha256: Sha256Hex
    s9_wheel_sha256: Sha256Hex
    s10_wheel_sha256: Sha256Hex
    consumer_receipts: tuple[ConsumerReceiptReference, ...]
    build_environment: BuildEnvironment
    test_summary: TestSummary

    @field_validator("module_ids")
    @classmethod
    def validate_modules(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        expected = {
            *(f"P9.S9.M{index:02d}" for index in range(1, 8)),
            *(f"P9.S10.M{index:02d}" for index in range(1, 5)),
        }
        if set(value) != expected or len(value) != 11:
            raise ValueError("S9-S10 delivery manifest must cover exactly 11 modules")
        return value


class ReleaseCandidateInputBundle(UtcTimestampedModel):
    s9_execution_envelope: S9ExecutionEnvelope
    source_cycle: CycleRef
    normalized_memory: NormalizedResearchMemoryBundle
    memory_and_p3_output: MemoryAndP3HandoffOutput
    feedback_effectiveness_output: FeedbackEffectivenessModuleOutput
    upstream_subphase_receipts: tuple[SubphaseReceiptReference, ...]
    consumer_receipts: tuple[ConsumerReceiptReference, ...]
    build_environment: BuildEnvironment
    test_summary: TestSummary
    source_tree_sha256: Sha256Hex
    s9_wheel_sha256: Sha256Hex
    s10_wheel_sha256: Sha256Hex
    test_report_ref: ArtifactReference
    source_tree_ref: ArtifactReference
    s9_wheel_ref: ArtifactReference
    s10_wheel_ref: ArtifactReference
    created_at: datetime

    @model_validator(mode="after")
    def validate_receipts(self) -> "ReleaseCandidateInputBundle":
        subphase_ids = {receipt.subphase_id for receipt in self.upstream_subphase_receipts}
        expected = {f"P9.S{index}" for index in range(1, 10)}
        if subphase_ids != expected:
            missing = sorted(expected - subphase_ids)
            extra = sorted(subphase_ids - expected)
            raise ValueError(f"release requires S1-S9 receipts; missing={missing}, extra={extra}")
        if len(self.consumer_receipts) < 4:
            raise ValueError("S9-S10 release requires consumer receipts for upstream phase bundles")
        receipt_cycles = {receipt.receipt_ref.cycle for receipt in self.upstream_subphase_receipts}
        if receipt_cycles != {self.source_cycle}:
            raise ValueError("all upstream subphase receipts must share the explicit source cycle")
        source_context = getattr(self.s9_execution_envelope.payload, "source_context", None)
        if source_context is not None and source_context.cycle != self.source_cycle:
            raise ValueError("S9 source context and S10 source cycle differ")
        if source_context is None:
            raise ValueError("S9 source context is required for release")
        expected_run = source_context.run_id
        receipt_runs = {receipt.receipt_ref.run_id for receipt in self.upstream_subphase_receipts}
        consumer_runs = {receipt.receipt_ref.run_id for receipt in self.consumer_receipts}
        if receipt_runs != {expected_run} or consumer_runs != {expected_run}:
            raise ValueError("release receipts must share the S9 source run")
        consumer_cycles = {receipt.receipt_ref.cycle for receipt in self.consumer_receipts}
        if consumer_cycles != {self.source_cycle}:
            raise ValueError("consumer receipts must share the release source cycle")
        authenticated = (
            (self.test_report_ref, self.test_summary.report_sha256, "P9.RELEASE.TEST_RUNNER"),
            (self.source_tree_ref, self.source_tree_sha256, "P9.RELEASE.SOURCE_TREE"),
            (self.s9_wheel_ref, self.s9_wheel_sha256, "P9.RELEASE.WHEEL_BUILDER"),
            (self.s10_wheel_ref, self.s10_wheel_sha256, "P9.RELEASE.WHEEL_BUILDER"),
        )
        for ref, expected_hash, producer in authenticated:
            if ref.run_id != expected_run or ref.cycle != self.source_cycle:
                raise ValueError("release evidence reference context mismatch")
            if ref.payload_sha256 != expected_hash or ref.producer_module_id != producer:
                raise ValueError("release evidence reference authentication failed")
        return self


class ReleaseCandidateOutput(StrictModel):
    release_state: ReleaseState
    release_manifest_without_s10: P9ReleaseManifest
    p0_authorization_manifest: P0AuthorizationRequestManifest
    p3_handoff_manifest_sha256: Sha256Hex
    feedback_distribution_manifest: FeedbackDistributionManifest
    phase09_delivery_manifest: Phase09DeliveryManifest
    reason_codes: tuple[ReasonCode, ...] = ()
    limitations: tuple[LongText, ...] = ()


class S10ExecutionBundle(UtcTimestampedModel):
    subphase_id: NonEmptyStr = "P9.S10"
    schema_version: NonEmptyStr = "1.0.0"
    normalization_result: ModuleResult[NormalizedResearchMemoryBundle]
    memory_handoff_result: ModuleResult[MemoryAndP3HandoffOutput]
    effectiveness_result: ModuleResult[FeedbackEffectivenessModuleOutput]
    release_candidate_result: ModuleResult[ReleaseCandidateOutput]
    subphase_state: S10SubphaseState
    created_at: datetime

    @field_validator("subphase_id")
    @classmethod
    def correct_subphase(cls, value: str) -> str:
        if value != "P9.S10":
            raise ValueError("execution bundle subphase_id must be P9.S10")
        return value


class S10ExecutionEnvelope(StrictModel):
    payload: S10ExecutionBundle
    payload_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_payload_hash(self) -> "S10ExecutionEnvelope":
        if self.payload_sha256 != sha256_hex(self.payload):
            raise ValueError("S10 execution envelope hash mismatch")
        return self


class P9ReleasePublicationManifest(StrictModel):
    release_id: NonEmptyStr
    all_subphase_receipts: tuple[SubphaseReceiptReference, ...]
    s10_execution_sha256: Sha256Hex
    candidate_release_manifest_sha256: Sha256Hex
    publication_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_publication(self) -> "P9ReleasePublicationManifest":
        ids = {receipt.subphase_id for receipt in self.all_subphase_receipts}
        expected = {f"P9.S{index}" for index in range(1, 11)}
        if ids != expected:
            raise ValueError("final publication must reference all 10 P9 subphases")
        payload = {
            "release_id": self.release_id,
            "all_subphase_receipts": self.all_subphase_receipts,
            "s10_execution_sha256": self.s10_execution_sha256,
            "candidate_release_manifest_sha256": self.candidate_release_manifest_sha256,
        }
        if self.publication_sha256 != sha256_hex(payload):
            raise ValueError("publication manifest hash mismatch")
        return self


class S10SubphaseDelivery(StrictModel):
    execution_envelope: S10ExecutionEnvelope
    publication_manifest: P9ReleasePublicationManifest | None = None
    delivery_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_delivery_hash(self) -> "S10SubphaseDelivery":
        payload = {
            "execution_envelope": self.execution_envelope,
            "publication_manifest": self.publication_manifest,
        }
        if self.delivery_sha256 != sha256_hex(payload):
            raise ValueError("S10 delivery hash mismatch")
        release_output = self.execution_envelope.payload.release_candidate_result.output
        if release_output is not None:
            ready = release_output.release_state in {
                ReleaseState.RELEASE_READY_FOR_P0,
                ReleaseState.RELEASE_READY_NO_PROMOTION,
            }
            if ready and self.publication_manifest is None:
                raise ValueError("ready S10 delivery requires publication manifest")
        return self
