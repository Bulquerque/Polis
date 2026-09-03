from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from ..enums import (
    DeploymentStage,
    GateSeverity,
    GateState,
    P0AuthorizationState,
    RecommendationState,
)
from .common import (
    ConfigId,
    CycleRef,
    EvidenceReference,
    LongText,
    NonEmptyStr,
    ReasonCode,
    Sha256Hex,
    StrictModel,
    UtcTimestampedModel,
)
from ..hashing import sha256_hex


class PromotionGateReceipt(StrictModel):
    gate_id: NonEmptyStr
    run_id: NonEmptyStr
    cycle: CycleRef
    subject_configuration_ids: tuple[ConfigId, ...]
    source_bundle_sha256: Sha256Hex
    producer_module_id: NonEmptyStr
    state: GateState
    severity: GateSeverity
    evidence_refs: tuple[EvidenceReference, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()
    limitations: tuple[LongText, ...] = ()
    receipt_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_failed_gate(self) -> "PromotionGateReceipt":
        if self.state == GateState.FAIL and not self.reason_codes:
            raise ValueError("failed promotion gates require reason codes")
        if not self.subject_configuration_ids or len(set(self.subject_configuration_ids)) != len(
            self.subject_configuration_ids
        ):
            raise ValueError("promotion gate receipt subjects must be non-empty and unique")
        expected = sha256_hex(self.model_dump(mode="json", exclude={"receipt_sha256"}))
        if self.receipt_sha256 != expected:
            raise ValueError("promotion gate receipt hash mismatch")
        return self


def build_promotion_gate_receipt(**values: object) -> PromotionGateReceipt:
    return PromotionGateReceipt(
        **values,
        receipt_sha256=sha256_hex(values),
    )


class PromotionEvidenceBundle(StrictModel):
    recommendation_candidate_id: ConfigId | None
    gate_receipts: tuple[PromotionGateReceipt, ...]
    favorable_evidence_refs: tuple[EvidenceReference, ...] = ()
    contrary_evidence_refs: tuple[EvidenceReference, ...] = ()
    limitations: tuple[LongText, ...] = ()
    rollback_requirements: tuple[LongText, ...] = ()

    @model_validator(mode="after")
    def validate_unique_gates(self) -> "PromotionEvidenceBundle":
        gate_ids = [receipt.gate_id for receipt in self.gate_receipts]
        if len(set(gate_ids)) != len(gate_ids):
            raise ValueError("promotion gate receipts must have unique gate IDs")
        return self


class PromotionRecommendation(UtcTimestampedModel):
    recommendation_id: NonEmptyStr
    recommendation_state: RecommendationState
    champion_configuration_id: ConfigId
    challenger_configuration_id: ConfigId | None
    requested_deployment_stage: DeploymentStage
    evidence_bundle: PromotionEvidenceBundle
    reason_codes: tuple[ReasonCode, ...]
    created_at: datetime
    authorization_required: bool = True

    @model_validator(mode="after")
    def validate_authority_boundary(self) -> "PromotionRecommendation":
        if not self.authorization_required:
            raise ValueError("P9 recommendations must always require P0 authorization")
        promotion_states = {
            RecommendationState.PROMOTE_RECOMMENDED,
            RecommendationState.LIMITED_CAPITAL_RECOMMENDED,
            RecommendationState.SHADOW_EXTENSION_RECOMMENDED,
            RecommendationState.CHALLENGER_ONLY,
        }
        recommends_challenger = self.recommendation_state in promotion_states
        if recommends_challenger and self.challenger_configuration_id is None:
            raise ValueError("challenger recommendations require a challenger configuration")
        return self


class P0PromotionAuthorizationRequest(UtcTimestampedModel):
    request_id: NonEmptyStr
    recommendation_id: NonEmptyStr
    recommendation_state: RecommendationState
    requested_deployment_stage: DeploymentStage
    authorization_state: P0AuthorizationState = P0AuthorizationState.PENDING_P0
    submitted_at: datetime
    evidence_bundle_sha256: NonEmptyStr

    @model_validator(mode="after")
    def preserve_p0_authority(self) -> "P0PromotionAuthorizationRequest":
        if self.authorization_state != P0AuthorizationState.PENDING_P0:
            raise ValueError("P9 can only submit requests pending P0 authorization")
        return self


class PromotionModuleOutput(StrictModel):
    evidence_bundle: PromotionEvidenceBundle
    recommendation: PromotionRecommendation
    p0_authorization_request: P0PromotionAuthorizationRequest
