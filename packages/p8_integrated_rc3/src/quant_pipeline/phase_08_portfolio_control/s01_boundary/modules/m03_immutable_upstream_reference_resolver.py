"""P8.S1.M03 — resolve historical P6/P5/P4 evidence by exact content hash."""

from __future__ import annotations

from collections.abc import Iterable

from quant_pipeline.phase_08_contracts.common import ArtifactReference
from quant_pipeline.phase_08_contracts.enums import (
    CandidateTerminalState,
    EvidenceResolutionStatus,
    ReceiptStatus,
)
from quant_pipeline.phase_08_contracts.p5 import P5BeliefEvidenceBundleV1
from quant_pipeline.phase_08_contracts.p6 import P6CandidateEconomicPackageV1
from quant_pipeline.phase_08_contracts.s1 import (
    CandidateTerminalRecord,
    CandidateTerminalStateLedger,
    M03Result,
    ResolvedArtifactReceipt,
    ResolvedCandidateEvidence,
    ResolvedCandidateEvidenceIndex,
    ValidatedP7HandoffBundle,
)

from ..context import S1ExecutionContext
from ..errors import ContractIntegrityError, LineageIntegrityError, TemporalIntegrityError
from ..module_support import build_receipt, read_verified_artifact, validate_model_json
from ..policies import ReferenceResolutionPolicy
from ..ports import ArtifactStorePort

MODULE_ID = "P8.S1.M03"


def _p5_references(bundle: P5BeliefEvidenceBundleV1) -> tuple[ArtifactReference, ...]:
    optional = (
        bundle.forecast_distribution_ref,
        bundle.quantile_panel_ref,
        bundle.scenario_set_ref,
        bundle.path_scenario_ref,
        bundle.covariance_dependence_ref,
        bundle.regime_state_ref,
        bundle.ood_state_ref,
        bundle.disagreement_ref,
        bundle.calibration_ref,
        bundle.ambiguity_evidence_ref,
        bundle.ensemble_weights_ref,
    )
    return tuple(reference for reference in optional if reference is not None) + bundle.view_refs + bundle.lineage_refs


def _deduplicate(references: Iterable[ArtifactReference]) -> tuple[ArtifactReference, ...]:
    by_id: dict[str, ArtifactReference] = {}
    for reference in references:
        prior = by_id.get(reference.artifact_id)
        if prior is not None and prior.content_sha256 != reference.content_sha256:
            raise LineageIntegrityError(
                f"artifact_id carries conflicting hashes: {reference.artifact_id}"
            )
        by_id[reference.artifact_id] = reference
    return tuple(by_id[key] for key in sorted(by_id))


def _resolve_lineage(
    references: Iterable[ArtifactReference],
    *,
    store: ArtifactStorePort,
    context: S1ExecutionContext,
    policy: ReferenceResolutionPolicy,
) -> tuple[ResolvedArtifactReceipt, ...]:
    receipts: list[ResolvedArtifactReceipt] = []
    for reference in _deduplicate(references):
        if policy.full_lineage_resolution:
            raw = read_verified_artifact(store, reference, decision_time=context.decision_time)
            receipts.append(
                ResolvedArtifactReceipt(
                    reference=reference,
                    status=EvidenceResolutionStatus.RESOLVED,
                    resolved_size_bytes=len(raw),
                )
            )
        else:
            receipts.append(
                ResolvedArtifactReceipt(
                    reference=reference,
                    status=EvidenceResolutionStatus.RESERVED,
                    reason_codes=("FULL_LINEAGE_RESOLUTION_DISABLED",),
                )
            )
    return tuple(receipts)


def _resolve_candidate(
    record: CandidateTerminalRecord,
    *,
    store: ArtifactStorePort,
    context: S1ExecutionContext,
    policy: ReferenceResolutionPolicy,
) -> ResolvedCandidateEvidence:
    candidate_id = record.candidate_id
    reference = record.p6_economic_package_ref
    if reference is None:
        if record.terminal_state is CandidateTerminalState.RANKED and policy.require_ranked_candidate_evidence:
            raise LineageIntegrityError(f"ranked candidate lacks P6 economic package: {candidate_id}")
        return ResolvedCandidateEvidence(
            candidate_id=candidate_id,
            status=EvidenceResolutionStatus.UNAVAILABLE,
            reference_receipts=(),
        )
    if reference.artifact_type != "P6_CANDIDATE_ECONOMIC_PACKAGE_V1":
        raise ContractIntegrityError(f"unexpected P6 artifact type for candidate {candidate_id}")
    p6_raw = read_verified_artifact(store, reference, decision_time=context.decision_time)
    p6 = validate_model_json(P6CandidateEconomicPackageV1, p6_raw, label=f"P6 package {candidate_id}")
    if p6.candidate_id != candidate_id:
        raise LineageIntegrityError(f"P6 candidate_id mismatch for {candidate_id}")
    if record.canonical_candidate_id is not None and p6.canonical_candidate_id != record.canonical_candidate_id:
        raise LineageIntegrityError(f"P6 canonical_candidate_id mismatch for {candidate_id}")
    for leg in p6.legs:
        if not (leg.contract_valid_from <= context.decision_time <= leg.contract_valid_until):
            raise TemporalIntegrityError(f"instrument contract is not valid at decision_time: {leg.instrument_id}")
    p5_ref = p6.p5_belief_bundle_ref
    if p5_ref.artifact_type != "P5_BELIEF_EVIDENCE_REFERENCE_BUNDLE_V1":
        raise ContractIntegrityError(f"unexpected P5 bundle artifact type for candidate {candidate_id}")
    p5_raw = read_verified_artifact(store, p5_ref, decision_time=context.decision_time)
    p5 = validate_model_json(P5BeliefEvidenceBundleV1, p5_raw, label=f"P5 bundle {candidate_id}")
    if p5.decision_time > context.decision_time:
        raise TemporalIntegrityError(f"P5 bundle is from the future for candidate {candidate_id}")
    if p5.as_of_time > context.market_cutoff_at:
        raise TemporalIntegrityError(f"P5 as_of_time exceeds market cutoff for candidate {candidate_id}")
    lineage = [reference, p5_ref, *p6.lineage_refs]
    lineage.extend(leg.instrument_master_ref for leg in p6.legs)
    lineage.extend(_p5_references(p5))
    receipts = _resolve_lineage(lineage, store=store, context=context, policy=policy)
    return ResolvedCandidateEvidence(
        candidate_id=candidate_id,
        status=EvidenceResolutionStatus.RESOLVED,
        p6_package=p6,
        p5_belief_bundle=p5,
        reference_receipts=receipts,
    )


def run_module(
    bundle: ValidatedP7HandoffBundle,
    ledger: CandidateTerminalStateLedger,
    *,
    store: ArtifactStorePort,
    context: S1ExecutionContext,
    policy: ReferenceResolutionPolicy,
) -> M03Result:
    handoff_artifact_receipts = _resolve_lineage(
        bundle.declared_artifact_refs,
        store=store,
        context=context,
        policy=policy,
    )
    candidates = tuple(
        _resolve_candidate(record, store=store, context=context, policy=policy) for record in ledger.records
    )
    index = ResolvedCandidateEvidenceIndex(
        candidates=candidates,
        handoff_artifact_receipts=handoff_artifact_receipts,
        full_lineage_resolution=policy.full_lineage_resolution,
    )
    receipt = build_receipt(
        module_id=MODULE_ID,
        status=ReceiptStatus.SEMANTICALLY_CONSUMED,
        inputs=(bundle, ledger),
        output=index,
        computed_at=context.computed_at,
    )
    return M03Result(evidence_index=index, receipt=receipt)
