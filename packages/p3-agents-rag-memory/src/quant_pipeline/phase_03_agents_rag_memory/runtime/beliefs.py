from __future__ import annotations

from collections.abc import Iterable
from statistics import fmean

from ..runtime_shared.s21_models import (
    ArtifactStatus,
    BeliefPayload,
    BeliefValueType,
    DirectionalBeliefPayload,
    Phase3RunSnapshot,
    PropositionRegistryConfig,
    RegimeBeliefPayload,
    RetrievalEvidenceMap,
    StructuredBeliefProposalPanel,
    ValidatedToolResultPanel,
    VolatilityBeliefPayload,
)
from ..runtime_shared.s22_errors import S22InvariantError, S22TemporalError
from ..runtime_shared.s22_hashing import content_hash, stable_id
from ..runtime_shared.s22_models import (
    BeliefDelta,
    BeliefOutcomeCommitmentLog,
    BeliefOutcomeCommitmentRecord,
    BeliefPolicyConfig,
    BeliefValidationStatus,
    BoundEvidenceRecord,
    CurrentBeliefStatePanel,
    CurrentBeliefStateRecord,
    EvidenceBindingStatus,
    EvidenceBoundBeliefUpdatePanel,
    EvidenceBoundBeliefUpdateRecord,
    EvidenceRelation,
    EvidenceSourceType,
    GraphEvidenceMap,
    RagIndexArtifact,
    ValidatedBeliefUpdatePanel,
    ValidatedBeliefUpdateRecord,
)


def _panel_status(statuses: Iterable[bool], *, empty: bool = False) -> ArtifactStatus:
    values = tuple(statuses)
    if empty:
        return ArtifactStatus.EMPTY_VALID
    if all(values):
        return ArtifactStatus.READY
    if any(values):
        return ArtifactStatus.DEGRADED
    return ArtifactStatus.FAILED


def _belief_key(person_id: str, underlying_id: str, proposition_id: str, horizon: str) -> tuple[str, str, str, str]:
    return (person_id, underlying_id, proposition_id, horizon)


def _payload_delta(prior: BeliefPayload | None, current: BeliefPayload) -> BeliefDelta:
    if isinstance(current, DirectionalBeliefPayload):
        prior_score = prior.score if isinstance(prior, DirectionalBeliefPayload) else 0.0
        delta = current.score - prior_score
        return BeliefDelta(
            value_type=BeliefValueType.DIRECTIONAL_SCORE,
            prior_payload=prior,
            accepted_payload=current,
            scalar_delta=delta,
            component_deltas={"score": delta},
            distance_l1=abs(delta),
        )
    if isinstance(current, VolatilityBeliefPayload):
        prior_level = prior.level if isinstance(prior, VolatilityBeliefPayload) else 0.0
        delta = current.level - prior_level
        return BeliefDelta(
            value_type=BeliefValueType.VOLATILITY_LEVEL,
            prior_payload=prior,
            accepted_payload=current,
            scalar_delta=delta,
            component_deltas={"level": delta},
            distance_l1=abs(delta),
        )
    if isinstance(current, RegimeBeliefPayload):
        prior_probabilities = prior.probabilities if isinstance(prior, RegimeBeliefPayload) else {}
        labels = sorted(set(prior_probabilities) | set(current.probabilities))
        components = {
            label: current.probabilities.get(label, 0.0) - prior_probabilities.get(label, 0.0)
            for label in labels
        }
        return BeliefDelta(
            value_type=BeliefValueType.REGIME_PROBABILITIES,
            prior_payload=prior,
            accepted_payload=current,
            component_deltas=components,
            distance_l1=sum(abs(value) for value in components.values()),
        )
    raise TypeError(f"unsupported belief payload: {type(current)!r}")


def _delta_allowed(delta: BeliefDelta, policy: BeliefPolicyConfig) -> bool:
    if delta.value_type == BeliefValueType.DIRECTIONAL_SCORE:
        return delta.distance_l1 <= policy.max_directional_score_delta
    if delta.value_type == BeliefValueType.VOLATILITY_LEVEL:
        return delta.distance_l1 <= policy.max_volatility_level_delta
    if delta.value_type == BeliefValueType.REGIME_PROBABILITIES:
        return delta.distance_l1 <= policy.max_regime_l1_delta
    return False


def validate_belief_state(
    *,
    proposals: StructuredBeliefProposalPanel,
    current_state: CurrentBeliefStatePanel,
    snapshot: Phase3RunSnapshot,
    proposition_registry: PropositionRegistryConfig,
    policy: BeliefPolicyConfig,
) -> ValidatedBeliefUpdatePanel:
    current_by_key: dict[tuple[str, str, str, str], CurrentBeliefStateRecord] = {}
    for state in current_state.records:
        key = _belief_key(state.person_id, state.underlying_id, state.proposition_id, state.horizon)
        if key in current_by_key:
            raise S22InvariantError(
                code="DUPLICATE_CURRENT_BELIEF_KEY",
                message=f"duplicate current belief key: {key}",
                module_id="P3.S22.M01",
            )
        current_by_key[key] = state

    proposal_keys: set[tuple[str, str, str, str]] = set()
    records: list[ValidatedBeliefUpdateRecord] = []
    accepted_flags: list[bool] = []
    for proposal in sorted(proposals.records, key=lambda item: item.belief_proposal_id):
        key = _belief_key(proposal.person_id, proposal.underlying_id, proposal.proposition_id, proposal.horizon)
        reason_codes: list[str] = []
        status = BeliefValidationStatus.ACCEPTED
        if key in proposal_keys:
            status = BeliefValidationStatus.REJECTED_DUPLICATE
            reason_codes.append("DUPLICATE_PROPOSAL_KEY")
        proposal_keys.add(key)

        try:
            definition = proposition_registry.get(proposal.proposition_id)
        except ValueError:
            definition = None
            status = BeliefValidationStatus.REJECTED_PROPOSITION
            reason_codes.append("PROPOSITION_NOT_REGISTERED")

        if definition is not None:
            if proposal.horizon not in definition.allowed_horizons:
                status = BeliefValidationStatus.REJECTED_HORIZON
                reason_codes.append("HORIZON_NOT_ALLOWED")
            if proposal.payload.value_type != definition.value_type:
                status = BeliefValidationStatus.REJECTED_PAYLOAD
                reason_codes.append("PAYLOAD_TYPE_MISMATCH")

        if proposal.generated_at > snapshot.as_of or proposal.as_of > snapshot.as_of:
            status = BeliefValidationStatus.REJECTED_TEMPORAL
            reason_codes.append("PROPOSAL_AFTER_SNAPSHOT")

        prior = current_by_key.get(key)
        if prior is None and not policy.allow_initial_belief:
            status = BeliefValidationStatus.REJECTED_PAYLOAD
            reason_codes.append("INITIAL_BELIEF_NOT_ALLOWED")

        delta = _payload_delta(prior.payload if prior else None, proposal.payload)
        if status == BeliefValidationStatus.ACCEPTED and not _delta_allowed(delta, policy):
            status = BeliefValidationStatus.REJECTED_DELTA_LIMIT
            reason_codes.append("DELTA_LIMIT_EXCEEDED")

        accepted = status == BeliefValidationStatus.ACCEPTED
        accepted_flags.append(accepted)
        records.append(
            ValidatedBeliefUpdateRecord(
                belief_update_id=stable_id(
                    "belief_update",
                    proposal.belief_proposal_id,
                    prior.belief_state_id if prior else "GENESIS",
                    snapshot.snapshot_id,
                ),
                proposal=proposal,
                prior_state=prior,
                validation_status=status,
                reason_codes=tuple(reason_codes),
                delta=delta if accepted else None,
                validated_at=snapshot.as_of,
                next_state_version=(prior.state_version + 1) if prior else 1,
                policy_version=policy.policy_version,
            )
        )

    return ValidatedBeliefUpdatePanel(
        status=_panel_status(accepted_flags, empty=not records),
        records=tuple(records),
        lineage=proposals.lineage.model_copy(update={"producer_module_id": "P3.S22.M01"}),
        reason_code=None if all(accepted_flags) else "ONE_OR_MORE_BELIEFS_REJECTED",
    )


def _index_evidence(
    *,
    retrieval: RetrievalEvidenceMap,
    graph: GraphEvidenceMap,
    rag: RagIndexArtifact,
    tool_results: ValidatedToolResultPanel,
    policy: BeliefPolicyConfig,
) -> dict[str, BoundEvidenceRecord]:
    index: dict[str, BoundEvidenceRecord] = {}

    def put(record: BoundEvidenceRecord) -> None:
        existing = index.get(record.evidence_id)
        if existing is not None and (
            existing.content_hash != record.content_hash or existing.source_type != record.source_type
        ):
            raise S22InvariantError(
                code="EVIDENCE_ID_COLLISION",
                message=f"evidence ID resolves to conflicting records: {record.evidence_id}",
                module_id="P3.S22.M02",
            )
        index[record.evidence_id] = record

    for item in retrieval.records:
        put(BoundEvidenceRecord(
            evidence_id=item.evidence_id,
            relation=EvidenceRelation.SUPPORTING,
            source_type=EvidenceSourceType.RETRIEVAL,
            source_id=item.source_id,
            available_at=item.available_at,
            content_hash=item.content_hash,
            source_quality=item.source_quality,
        ))
    for item in graph.records:
        put(BoundEvidenceRecord(
            evidence_id=item.evidence_id,
            relation=EvidenceRelation.SUPPORTING,
            source_type=EvidenceSourceType.GRAPH,
            source_id=item.source_id,
            available_at=item.available_at,
            content_hash=item.content_hash,
            source_quality=item.source_quality,
        ))
    for item in rag.records:
        put(BoundEvidenceRecord(
            evidence_id=item.evidence_id,
            relation=EvidenceRelation.SUPPORTING,
            source_type=EvidenceSourceType.RAG,
            source_id=item.source_id,
            available_at=item.available_at,
            content_hash=item.content_hash,
            source_quality=item.source_quality,
        ))
    for item in tool_results.records:
        raw = item.raw_result
        if item.validation_status.value != "VALID" or raw.available_at is None or raw.response_hash is None:
            continue
        base = BoundEvidenceRecord(
            evidence_id=raw.execution_id,
            relation=EvidenceRelation.SUPPORTING,
            source_type=EvidenceSourceType.TOOL,
            source_id=raw.provider_id,
            available_at=raw.available_at,
            content_hash=raw.response_hash,
            source_quality=policy.tool_result_source_quality,
        )
        put(base)
        for evidence_id in raw.evidence_refs:
            put(base.model_copy(update={"evidence_id": evidence_id}))
    return index


def bind_evidence(
    *,
    updates: ValidatedBeliefUpdatePanel,
    retrieval: RetrievalEvidenceMap,
    graph: GraphEvidenceMap,
    rag: RagIndexArtifact,
    tool_results: ValidatedToolResultPanel,
    policy: BeliefPolicyConfig,
) -> EvidenceBoundBeliefUpdatePanel:
    index = _index_evidence(
        retrieval=retrieval,
        graph=graph,
        rag=rag,
        tool_results=tool_results,
        policy=policy,
    )
    records: list[EvidenceBoundBeliefUpdateRecord] = []
    bound_flags: list[bool] = []
    for update in updates.records:
        proposal = update.proposal
        supporting_refs = tuple(dict.fromkeys(proposal.supporting_evidence_refs))
        opposing_refs = tuple(dict.fromkeys(proposal.opposing_evidence_refs))
        supporting_set = set(supporting_refs)
        opposing_set = set(opposing_refs)
        overlap = sorted(supporting_set & opposing_set)
        if update.validation_status != BeliefValidationStatus.ACCEPTED:
            status = EvidenceBindingStatus.UPSTREAM_REJECTED
            reason_codes = ("UPSTREAM_BELIEF_REJECTED",)
            supporting: list[BoundEvidenceRecord] = []
            opposing: list[BoundEvidenceRecord] = []
            unresolved: list[str] = []
            future: list[str] = []
        else:
            unresolved = [ref for ref in supporting_refs + opposing_refs if ref not in index]
            future = [
                ref for ref in supporting_refs + opposing_refs
                if ref in index and index[ref].available_at > proposal.as_of
            ]
            supporting = [
                index[ref].model_copy(update={"relation": EvidenceRelation.SUPPORTING})
                for ref in supporting_refs if ref in index and ref not in future
            ]
            opposing = [
                index[ref].model_copy(update={"relation": EvidenceRelation.OPPOSING})
                for ref in opposing_refs if ref in index and ref not in future
            ]
            reason_list: list[str] = []
            if overlap:
                status = EvidenceBindingStatus.SUPPORT_OPPOSITION_OVERLAP
                reason_list.append("SUPPORT_OPPOSITION_OVERLAP")
            elif future:
                status = EvidenceBindingStatus.FUTURE_EVIDENCE
                reason_list.append("EVIDENCE_AFTER_AS_OF")
            elif unresolved:
                status = EvidenceBindingStatus.INVALID_REFERENCE
                reason_list.append("UNRESOLVED_EVIDENCE_REF")
            elif len(supporting) < policy.minimum_supporting_evidence:
                status = EvidenceBindingStatus.INSUFFICIENT_EVIDENCE
                reason_list.append("MINIMUM_SUPPORT_NOT_MET")
            else:
                status = EvidenceBindingStatus.BOUND
            reason_codes = tuple(reason_list)

        expected_count = len(supporting_refs) + len(opposing_refs)
        resolved_count = len(supporting) + len(opposing)
        coverage = 1.0 if expected_count == 0 and status == EvidenceBindingStatus.BOUND else (
            resolved_count / expected_count if expected_count else 0.0
        )
        qualities = [item.source_quality for item in supporting + opposing]
        mean_quality = fmean(qualities) if qualities else 0.0
        is_bound = status == EvidenceBindingStatus.BOUND
        bound_flags.append(is_bound)
        records.append(EvidenceBoundBeliefUpdateRecord(
            validated_update=update,
            binding_status=status,
            supporting_evidence=tuple(supporting),
            opposing_evidence=tuple(opposing),
            unresolved_refs=tuple(sorted(unresolved)),
            future_refs=tuple(sorted(future)),
            evidence_coverage=coverage,
            mean_source_quality=mean_quality,
            reason_codes=reason_codes,
            bound_at=update.validated_at,
        ))

    return EvidenceBoundBeliefUpdatePanel(
        status=_panel_status(bound_flags, empty=not records),
        records=tuple(records),
        lineage=updates.lineage.model_copy(update={"producer_module_id": "P3.S22.M02"}),
        reason_code=None if all(bound_flags) else "ONE_OR_MORE_BINDINGS_NOT_COMMITTABLE",
    )


def _direction_summary(payload: BeliefPayload) -> str:
    if isinstance(payload, DirectionalBeliefPayload):
        return payload.direction
    if isinstance(payload, VolatilityBeliefPayload):
        return f"LEVEL_{payload.level:.6f}"
    if isinstance(payload, RegimeBeliefPayload):
        return max(payload.probabilities.items(), key=lambda item: (item[1], item[0]))[0]
    raise TypeError(f"unsupported belief payload: {type(payload)!r}")


def log_commitments(
    *,
    bound_updates: EvidenceBoundBeliefUpdatePanel,
    snapshot: Phase3RunSnapshot,
    policy: BeliefPolicyConfig,
) -> BeliefOutcomeCommitmentLog:
    eligible = [
        item for item in bound_updates.records
        if item.binding_status == EvidenceBindingStatus.BOUND
        and item.validated_update.validation_status == BeliefValidationStatus.ACCEPTED
    ]
    commitments: list[BeliefOutcomeCommitmentRecord] = []
    seen_keys: set[tuple[str, str, str, str]] = set()
    for item in sorted(eligible, key=lambda record: record.validated_update.belief_update_id):
        update = item.validated_update
        proposal = update.proposal
        key = _belief_key(proposal.person_id, proposal.underlying_id, proposal.proposition_id, proposal.horizon)
        if key in seen_keys:
            raise S22InvariantError(
                code="DUPLICATE_COMMITMENT_KEY",
                message=f"multiple committable updates for key: {key}",
                module_id="P3.S22.M03",
            )
        seen_keys.add(key)
        matures_at = proposal.generated_at + policy.maturity_delta(proposal.horizon)
        if snapshot.as_of >= matures_at:
            raise S22TemporalError(
                code="LATE_COMMITMENT",
                message=f"commitment would occur at or after maturity: {key}",
                module_id="P3.S22.M03",
                details={"matures_at": matures_at.isoformat(), "as_of": snapshot.as_of.isoformat()},
            )
        evidence_refs = tuple(sorted({e.evidence_id for e in item.supporting_evidence + item.opposing_evidence}))
        payload_json = proposal.payload.model_dump(mode="json")
        hash_payload = {
            "run_id": snapshot.run_id,
            "cycle_id": snapshot.cycle_id,
            "snapshot_id": snapshot.snapshot_id,
            "person_id": proposal.person_id,
            "underlying_id": proposal.underlying_id,
            "proposition_id": proposal.proposition_id,
            "horizon": proposal.horizon,
            "value_payload": payload_json,
            "strength": proposal.strength,
            "confidence": proposal.confidence,
            "uncertainty": proposal.uncertainty,
            "evidence_refs": evidence_refs,
            "generated_at": proposal.generated_at,
            "committed_at": snapshot.as_of,
            "matures_at": matures_at,
        }
        commit_hash = content_hash(hash_payload)
        commitments.append(BeliefOutcomeCommitmentRecord(
            commitment_id=stable_id("commitment", commit_hash),
            person_id=proposal.person_id,
            subject=proposal.underlying_id,
            proposition=proposal.proposition_id,
            direction=_direction_summary(proposal.payload),
            strength=proposal.strength,
            confidence=proposal.confidence,
            uncertainty=proposal.uncertainty,
            horizon=proposal.horizon,
            value_payload=payload_json,
            evidence_refs=evidence_refs,
            belief_update_id=update.belief_update_id,
            run_id=snapshot.run_id,
            cycle_id=snapshot.cycle_id,
            snapshot_id=snapshot.snapshot_id,
            generated_at=proposal.generated_at,
            committed_at=snapshot.as_of,
            matures_at=matures_at,
            commit_hash=commit_hash,
            lineage_id=bound_updates.lineage.lineage_id,
        ))

    return BeliefOutcomeCommitmentLog(
        status=ArtifactStatus.READY if commitments else ArtifactStatus.EMPTY_VALID,
        records=tuple(commitments),
        lineage=bound_updates.lineage.model_copy(update={"producer_module_id": "P3.S22.M03"}),
        reason_code=None if commitments else "NO_COMMITTABLE_BELIEFS",
    )
