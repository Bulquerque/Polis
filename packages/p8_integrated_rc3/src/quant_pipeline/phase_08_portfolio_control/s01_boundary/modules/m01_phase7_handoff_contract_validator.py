"""P8.S1.M01 — validate the P7 handoff without interpreting portfolio economics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from quant_pipeline.phase_08_contracts.common import ArtifactConsumptionReceipt, ArtifactReference
from quant_pipeline.phase_08_contracts.enums import P7TerminalState, ReceiptStatus
from quant_pipeline.phase_08_contracts.p7 import P7RankingHandoffV1
from quant_pipeline.phase_08_contracts.s1 import CompatibilityDecision, M01Result, ValidatedP7HandoffBundle

from ..context import S1ExecutionContext
from ..errors import CandidateConservationError, ContractIntegrityError, TemporalIntegrityError
from ..module_support import build_receipt, load_json_object, validate_model_json, verify_model_embedded_hash
from ..policies import ContractCompatibilityPolicy

MODULE_ID = "P8.S1.M01"


def _find_forbidden_fields(value: object, forbidden: frozenset[str], path: str = "$") -> tuple[str, ...]:
    matches: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in forbidden:
                matches.append(child_path)
            matches.extend(_find_forbidden_fields(child, forbidden, child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            matches.extend(_find_forbidden_fields(child, forbidden, f"{path}[{index}]"))
    return tuple(matches)


def _validate_partition(handoff: P7RankingHandoffV1) -> None:
    population_lists = {
        "ranked": [row.candidate_id for row in handoff.ranked],
        "eligibility_blocked": [row.candidate_id for row in handoff.eligibility_blocked],
        "safety_blocked": [row.candidate_id for row in handoff.safety_blocked],
        "abstained": [row.candidate_id for row in handoff.abstained],
    }
    for name, candidate_ids in population_lists.items():
        if len(candidate_ids) != len(set(candidate_ids)):
            raise CandidateConservationError(f"{name} contains duplicate candidate IDs")
    populations = {name: set(candidate_ids) for name, candidate_ids in population_lists.items()}
    all_rows = [candidate_id for candidate_ids in population_lists.values() for candidate_id in candidate_ids]
    if len(all_rows) != len(set(all_rows)):
        raise CandidateConservationError("candidate appears in more than one terminal population")
    if set(handoff.received_candidate_ids) != set(all_rows):
        raise CandidateConservationError("received candidates do not equal terminal populations")
    expected_states = {
        "eligibility_blocked": P7TerminalState.ELIGIBILITY_BLOCKED,
        "safety_blocked": P7TerminalState.SAFETY_BLOCKED,
        "abstained": P7TerminalState.ABSTAINED,
    }
    for name, expected_state in expected_states.items():
        rows = getattr(handoff, name)
        if any(row.terminal_state is not expected_state for row in rows):
            raise CandidateConservationError(f"{name} contains an incompatible terminal state")


def _validate_groups(handoff: P7RankingHandoffV1) -> None:
    group_by_id = {group.comparison_group_id: group for group in handoff.comparison_groups}
    ranked_by_group: dict[str, list[tuple[int, str]]] = {}
    for row in handoff.ranked:
        group = group_by_id.get(row.comparison_group_id)
        if group is None:
            raise ContractIntegrityError(f"unknown comparison group: {row.comparison_group_id}")
        if row.candidate_id not in group.member_candidate_ids:
            raise ContractIntegrityError(f"ranked candidate absent from comparison group: {row.candidate_id}")
        ranked_by_group.setdefault(row.comparison_group_id, []).append((row.rank, row.candidate_id))
        if row.p6_economic_package_ref.artifact_type != "P6_CANDIDATE_ECONOMIC_PACKAGE_V1":
            raise ContractIntegrityError("ranked candidate P6 reference has unexpected artifact_type")
    for group_id, rows in ranked_by_group.items():
        ranks = sorted(rank for rank, _ in rows)
        if len(ranks) != len(set(ranks)):
            raise ContractIntegrityError(f"duplicate rank inside comparison group: {group_id}")
        if ranks != list(range(1, len(ranks) + 1)):
            raise ContractIntegrityError(f"ranks must be contiguous inside comparison group: {group_id}")


def _embedded_references(handoff: P7RankingHandoffV1) -> tuple[ArtifactReference, ...]:
    references: list[ArtifactReference] = list(handoff.artifact_refs)
    for row in handoff.ranked:
        references.extend((row.p6_economic_package_ref, row.decision_trace_ref))
        references.extend(
            reference
            for reference in (
                row.confidence_calibration_ref,
                row.thesis_card_ref,
                row.score_decomposition_ref,
            )
            if reference is not None
        )
    for rows in (handoff.eligibility_blocked, handoff.safety_blocked, handoff.abstained):
        for row in rows:
            if row.p6_economic_package_ref is not None:
                references.append(row.p6_economic_package_ref)
            references.extend(row.missing_evidence_refs)
    by_id: dict[str, ArtifactReference] = {}
    for reference in references:
        prior = by_id.get(reference.artifact_id)
        if prior is not None and prior.content_sha256 != reference.content_sha256:
            raise ContractIntegrityError(
                f"artifact_id carries conflicting hashes in P7 handoff: {reference.artifact_id}"
            )
        by_id[reference.artifact_id] = reference
    return tuple(by_id[key] for key in sorted(by_id))


def run_module(
    raw_handoff: bytes,
    *,
    context: S1ExecutionContext,
    policy: ContractCompatibilityPolicy,
) -> M01Result:
    raw_object = load_json_object(raw_handoff)
    forbidden_paths = _find_forbidden_fields(raw_object, policy.forbidden_fields)
    if forbidden_paths:
        raise ContractIntegrityError(f"forbidden fields detected: {forbidden_paths}")
    handoff = validate_model_json(P7RankingHandoffV1, raw_handoff, label="P7 handoff")
    verify_model_embedded_hash(handoff)
    if handoff.contract_version not in policy.accepted_contract_versions:
        raise ContractIntegrityError(f"unsupported contract version: {handoff.contract_version}")
    if handoff.schema_version not in policy.accepted_schema_versions:
        raise ContractIntegrityError(f"unsupported schema version: {handoff.schema_version}")
    if handoff.producer_phase not in policy.accepted_producer_phases:
        raise ContractIntegrityError(f"unexpected producer phase: {handoff.producer_phase}")
    if handoff.run_id != context.run_id or handoff.cycle_id != context.cycle_id:
        raise TemporalIntegrityError("P7 handoff run/cycle does not match the P8 execution context")
    if handoff.decision_time > context.decision_time:
        raise TemporalIntegrityError("P7 handoff decision_time is after the P8 decision_time")
    if handoff.market_cutoff_at != context.market_cutoff_at:
        raise TemporalIntegrityError("P7 handoff market_cutoff_at does not match the P8 execution context")
    if handoff.available_at > context.decision_time:
        raise TemporalIntegrityError("P7 handoff was not available at P8 decision_time")
    references = _embedded_references(handoff)
    if any(reference.available_at > context.decision_time for reference in references):
        raise TemporalIntegrityError("handoff contains an artifact unavailable at P8 decision_time")
    _validate_partition(handoff)
    _validate_groups(handoff)
    artifact_receipts = tuple(
        ArtifactConsumptionReceipt(
            artifact_id=reference.artifact_id,
            artifact_type=reference.artifact_type,
            status=ReceiptStatus.REFERENCE_DECLARED,
            consumer_module_id=MODULE_ID,
            input_hash=reference.content_sha256,
        )
        for reference in references
    )
    bundle = ValidatedP7HandoffBundle(
        handoff=handoff,
        compatibility=CompatibilityDecision(contract_mode="FULL_NATIVE"),
        declared_artifact_refs=references,
        artifact_receipts=artifact_receipts,
    )
    receipt = build_receipt(
        module_id=MODULE_ID,
        status=ReceiptStatus.ACCEPTED,
        inputs=(raw_object,),
        output=bundle,
        computed_at=context.computed_at,
    )
    return M01Result(bundle=bundle, receipt=receipt)
