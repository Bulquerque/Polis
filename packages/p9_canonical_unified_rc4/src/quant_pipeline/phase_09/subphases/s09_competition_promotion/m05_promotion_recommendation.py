from __future__ import annotations

from datetime import datetime

from .enums import (
    ChallengerQualificationState,
    DeploymentStage,
    GateSeverity,
    GateState,
    ModuleStatus,
    RecommendationState,
)
from .hashing import sha256_hex
from .models.common import ModuleDiagnostics, ModuleResult, build_module_result
from .models.policy import CompetitionObjectivePolicy
from .models.promotion import (
    P0PromotionAuthorizationRequest,
    PromotionEvidenceBundle,
    PromotionGateReceipt,
    PromotionModuleOutput,
    PromotionRecommendation,
)
from .models.qualification import ChampionChallengerQualificationReport
from .models.execution import PromotionSourceContext

MODULE_ID = "P9.S9.M05"


def _map_qualification_state(
    qualification_state: ChallengerQualificationState,
) -> tuple[RecommendationState, DeploymentStage]:
    mapping = {
        ChallengerQualificationState.CHALLENGER_QUALIFIED: (
            RecommendationState.PROMOTE_RECOMMENDED,
            DeploymentStage.FULL_PRODUCTION,
        ),
        ChallengerQualificationState.CHALLENGER_QUALIFIED_LIMITED_CAPITAL: (
            RecommendationState.LIMITED_CAPITAL_RECOMMENDED,
            DeploymentStage.LIMITED_CAPITAL,
        ),
        ChallengerQualificationState.CHALLENGER_SHADOW_ONLY: (
            RecommendationState.SHADOW_EXTENSION_RECOMMENDED,
            DeploymentStage.SHADOW_ONLY,
        ),
        ChallengerQualificationState.RETAIN_CHAMPION: (
            RecommendationState.RETAIN_CHAMPION,
            DeploymentStage.RETAIN_CURRENT,
        ),
        ChallengerQualificationState.STATISTICALLY_INDISTINGUISHABLE: (
            RecommendationState.RETAIN_CHAMPION,
            DeploymentStage.RETAIN_CURRENT,
        ),
        ChallengerQualificationState.QUARANTINE_CHALLENGER: (
            RecommendationState.QUARANTINE_RECOMMENDED,
            DeploymentStage.QUARANTINE,
        ),
        ChallengerQualificationState.INSUFFICIENT_EVIDENCE: (
            RecommendationState.INSUFFICIENT_EVIDENCE,
            DeploymentStage.RETAIN_CURRENT,
        ),
        ChallengerQualificationState.COMPARISON_INVALID: (
            RecommendationState.REQUALIFICATION_REQUIRED,
            DeploymentStage.RETAIN_CURRENT,
        ),
    }
    return mapping[qualification_state]


def build_promotion_recommendation(
    *,
    objective: CompetitionObjectivePolicy,
    qualification: ChampionChallengerQualificationReport,
    gate_receipts: tuple[PromotionGateReceipt, ...],
    source_context: PromotionSourceContext,
    created_at: datetime,
) -> ModuleResult[PromotionModuleOutput]:
    """Aggregate gate evidence and produce a recommendation pending P0 authorization."""

    for receipt in gate_receipts:
        if receipt.run_id != source_context.run_id or receipt.cycle != source_context.cycle:
            raise ValueError("promotion gate receipt context mismatch")
        if receipt.source_bundle_sha256 != source_context.attribution_bundle_sha256:
            raise ValueError("promotion gate receipt source bundle mismatch")
        if (
            qualification.recommended_challenger_id is not None
            and qualification.recommended_challenger_id
            not in receipt.subject_configuration_ids
        ):
            raise ValueError("promotion gate receipt challenger mismatch")
    gate_map = {receipt.gate_id: receipt for receipt in gate_receipts}
    required_gate_ids = {rule.gate_id for rule in objective.hard_gates}
    missing = tuple(sorted(required_gate_ids - set(gate_map)))
    critical_failures = tuple(
        receipt
        for receipt in gate_receipts
        if receipt.state == GateState.FAIL
        and receipt.severity in {GateSeverity.BLOCKING, GateSeverity.CRITICAL}
    )
    evidence_refs = tuple(
        reference
        for receipt in gate_receipts
        for reference in receipt.evidence_refs
    )
    limitations = tuple(
        limitation
        for receipt in gate_receipts
        for limitation in receipt.limitations
    )
    contrary = tuple(
        reference
        for receipt in gate_receipts
        if receipt.state in {GateState.FAIL, GateState.INSUFFICIENT_EVIDENCE}
        for reference in receipt.evidence_refs
    )
    favorable = tuple(
        reference
        for receipt in gate_receipts
        if receipt.state in {GateState.PASS, GateState.PASS_WITH_LIMITATIONS}
        for reference in receipt.evidence_refs
    )

    recommendation_state, stage = _map_qualification_state(qualification.report_state)
    reason_codes: list[str] = []
    if missing:
        recommendation_state = RecommendationState.INSUFFICIENT_EVIDENCE
        stage = DeploymentStage.RETAIN_CURRENT
        reason_codes.append("P9_PROMOTION_REQUIRED_GATE_MISSING")
        limitations = (*limitations, f"missing required gates: {', '.join(missing)}")
    if critical_failures:
        recommendation_state = RecommendationState.QUARANTINE_RECOMMENDED
        stage = DeploymentStage.QUARANTINE
        reason_codes.append("P9_PROMOTION_CRITICAL_GATE_FAILED")
    if qualification.report_state == ChallengerQualificationState.INSUFFICIENT_EVIDENCE:
        reason_codes.append("P9_PROMOTION_INSUFFICIENT_EVIDENCE")
    if qualification.report_state == ChallengerQualificationState.COMPARISON_INVALID:
        reason_codes.append("P9_PROMOTION_CHAMPION_CHALLENGER_COMPARISON_INVALID")
    if not reason_codes:
        reason_codes.append("P9_PROMOTION_RECOMMENDATION_COMPILED")

    rollback_requirements: tuple[str, ...]
    if stage in {DeploymentStage.FULL_PRODUCTION, DeploymentStage.LIMITED_CAPITAL}:
        rollback_requirements = (
            "preserve champion artifact and deployment receipt",
            "define live degradation threshold and rollback owner",
            "retain deterministic replay bundle for both champion and challenger",
        )
    elif stage == DeploymentStage.SHADOW_ONLY:
        rollback_requirements = ("no capital deployment; continue shadow evidence collection",)
    else:
        rollback_requirements = ()

    evidence_bundle = PromotionEvidenceBundle(
        recommendation_candidate_id=qualification.recommended_challenger_id,
        gate_receipts=tuple(sorted(gate_receipts, key=lambda receipt: receipt.gate_id)),
        favorable_evidence_refs=favorable,
        contrary_evidence_refs=contrary,
        limitations=limitations,
        rollback_requirements=rollback_requirements,
    )
    recommendation_id = f"rec-{sha256_hex((qualification, evidence_bundle))[:16]}"
    recommendation = PromotionRecommendation(
        recommendation_id=recommendation_id,
        recommendation_state=recommendation_state,
        champion_configuration_id=qualification.champion_configuration_id,
        challenger_configuration_id=qualification.recommended_challenger_id,
        requested_deployment_stage=stage,
        evidence_bundle=evidence_bundle,
        reason_codes=tuple(reason_codes),
        created_at=created_at,
        authorization_required=True,
    )
    request = P0PromotionAuthorizationRequest(
        request_id=f"p0-{sha256_hex(recommendation)[:16]}",
        recommendation_id=recommendation.recommendation_id,
        recommendation_state=recommendation.recommendation_state,
        requested_deployment_stage=recommendation.requested_deployment_stage,
        submitted_at=created_at,
        evidence_bundle_sha256=sha256_hex(evidence_bundle),
    )
    output = PromotionModuleOutput(
        evidence_bundle=evidence_bundle,
        recommendation=recommendation,
        p0_authorization_request=request,
    )
    status = (
        ModuleStatus.INSUFFICIENT_EVIDENCE
        if recommendation_state == RecommendationState.INSUFFICIENT_EVIDENCE
        else ModuleStatus.SUCCESS
    )
    return build_module_result(
        module_id=MODULE_ID,
        status=status,
        output=output,
        reason_codes=(
            ("P9_PROMOTION_INSUFFICIENT_EVIDENCE",)
            if status == ModuleStatus.INSUFFICIENT_EVIDENCE
            else ()
        ),
        diagnostics=ModuleDiagnostics(
            counters=(
                ("required_gate_count", len(required_gate_ids)),
                ("received_gate_count", len(gate_receipts)),
                ("critical_failure_count", len(critical_failures)),
            ),
            trace=("P9 recommendation compiled without production authorization",),
        ),
    )
