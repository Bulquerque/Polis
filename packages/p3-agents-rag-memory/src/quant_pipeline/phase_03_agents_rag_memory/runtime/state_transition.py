from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from math import isclose
from statistics import fmean

from ..runtime_shared.s21_models import ArtifactStatus, LineageRecord
from ..runtime_shared.s22_models import (
    BeliefValidationStatus,
    CurrentBeliefStatePanel,
    CurrentBeliefStateRecord,
    EvidenceBindingStatus,
    EvidenceBoundBeliefUpdatePanel,
    EvidenceBoundBeliefUpdateRecord,
)
from ..runtime_shared.s23_errors import S23InvariantError, S23TemporalError
from ..runtime_shared.s23_hashing import stable_id
from ..runtime_shared.s23_models import (
    CurrentPersonStatePanel,
    CurrentPersonStateRecord,
    NextBeliefStatePanel,
    NextBeliefStateRecord,
    NextPersonStatePanel,
    NextPersonStateRecord,
    PersonFieldChange,
    PersonSchemaPolicy,
    RejectedPersonStateTransition,
    StateChangeConfig,
    StateSpeedClass,
    TransitionStatus,
    ValidatedNextPersonStatePanel,
)

_STATE_FAMILIES = (
    "core_personality",
    "cognitive_capacity",
    "knowledge",
    "trust",
    "tool_proficiency",
    "attention",
    "confidence",
    "functional_affect",
)


def _panel_status(flags: Iterable[bool], *, empty: bool = False) -> ArtifactStatus:
    values = tuple(flags)
    if empty:
        return ArtifactStatus.EMPTY_VALID
    if all(values):
        return ArtifactStatus.READY
    if any(values):
        return ArtifactStatus.DEGRADED
    return ArtifactStatus.FAILED


def _unique_by(items: Iterable[object], key_getter, *, code: str, module_id: str) -> dict[object, object]:
    result: dict[object, object] = {}
    for item in items:
        key = key_getter(item)
        if key in result:
            raise S23InvariantError(code=code, message=f"duplicate key: {key}", module_id=module_id)
        result[key] = item
    return result


def _elapsed_days(start: datetime, end: datetime, *, module_id: str) -> float:
    if end < start:
        raise S23TemporalError(
            code="TRANSITION_BEFORE_PRIOR_STATE",
            message=f"transition time {end.isoformat()} precedes {start.isoformat()}",
            module_id=module_id,
        )
    return (end - start).total_seconds() / 86400.0


def _allowed_delta(speed: StateSpeedClass, elapsed_days: float, config: StateChangeConfig) -> float:
    if speed is StateSpeedClass.FAST:
        return config.fast_max_delta_per_cycle
    months = elapsed_days / config.average_calendar_days_per_month
    if speed is StateSpeedClass.SLOW:
        return min(1.0, config.slow_max_delta_per_month * months)
    return min(1.0, config.medium_max_delta_per_month * months)


def _clamped_change(
    *,
    family: str,
    field: str,
    prior: float,
    target: float,
    transition_at: datetime,
    prior_updated_at: datetime,
    policy: PersonSchemaPolicy,
    config: StateChangeConfig,
    reason_code: str,
    evidence_refs: tuple[str, ...] = (),
    cause_ids: tuple[str, ...] = (),
) -> PersonFieldChange | None:
    speed = policy.speed_for(family)
    elapsed = _elapsed_days(prior_updated_at, transition_at, module_id="P3.S23.M01")
    allowed = _allowed_delta(speed, elapsed, config)
    requested = max(-allowed, min(allowed, target - prior))
    accepted = max(0.0, min(1.0, prior + requested))
    delta = accepted - prior
    if isclose(delta, 0.0, abs_tol=config.numeric_tolerance):
        return None
    return PersonFieldChange(
        field_path=f"{family}.{field}",
        speed_class=speed,
        prior_value=prior,
        candidate_value=max(0.0, min(1.0, target)),
        accepted_value=accepted,
        delta=delta,
        allowed_delta=allowed,
        reason_code=reason_code,
        evidence_refs=evidence_refs,
        cause_ids=cause_ids,
    )


def _replace_map_value(state: CurrentPersonStateRecord, field_path: str, value: float) -> CurrentPersonStateRecord:
    family, key = field_path.split(".", 1)
    mapping = dict(getattr(state, family))
    mapping[key] = value
    return state.model_copy(update={family: mapping})


def _belief_key(record: CurrentBeliefStateRecord | NextBeliefStateRecord) -> tuple[str, str, str, str]:
    return (record.person_id, record.underlying_id, record.proposition_id, record.horizon)


def _committable_updates(
    belief_updates: EvidenceBoundBeliefUpdatePanel,
    persons: Mapping[object, object],
) -> tuple[tuple[EvidenceBoundBeliefUpdateRecord, ...], dict[str, list[EvidenceBoundBeliefUpdateRecord]]]:
    records = tuple(
        item for item in belief_updates.records
        if item.binding_status is EvidenceBindingStatus.BOUND
        and item.validated_update.validation_status is BeliefValidationStatus.ACCEPTED
    )
    by_person: dict[str, list[EvidenceBoundBeliefUpdateRecord]] = defaultdict(list)
    accepted_keys: set[tuple[str, str, str, str]] = set()
    for record in records:
        proposal = record.validated_update.proposal
        key = (proposal.person_id, proposal.underlying_id, proposal.proposition_id, proposal.horizon)
        if key in accepted_keys:
            raise S23InvariantError(
                code="DUPLICATE_ACCEPTED_BELIEF_UPDATE",
                message=f"duplicate accepted belief update key: {key}",
                module_id="P3.S23.M01",
            )
        accepted_keys.add(key)
        if proposal.person_id not in persons:
            raise S23InvariantError(
                code="BELIEF_PERSON_NOT_FOUND",
                message=f"belief update references missing person {proposal.person_id}",
                module_id="P3.S23.M01",
            )
        by_person[proposal.person_id].append(record)
    return records, by_person


def _next_belief_states(
    current_by_key: Mapping[object, object],
    updates: tuple[EvidenceBoundBeliefUpdateRecord, ...],
) -> dict[tuple[str, str, str, str], NextBeliefStateRecord]:
    result: dict[tuple[str, str, str, str], NextBeliefStateRecord] = {}
    for key, untyped_prior in current_by_key.items():
        assert isinstance(untyped_prior, CurrentBeliefStateRecord)
        prior = untyped_prior
        result[key] = NextBeliefStateRecord(
            belief_state_id=prior.belief_state_id,
            prior_belief_state_id=prior.belief_state_id,
            person_id=prior.person_id,
            underlying_id=prior.underlying_id,
            proposition_id=prior.proposition_id,
            horizon=prior.horizon,
            payload=prior.payload,
            prior_payload=prior.payload,
            confidence=prior.confidence,
            uncertainty=prior.uncertainty,
            evidence_refs=prior.evidence_refs,
            updated_at=prior.updated_at,
            state_version=prior.state_version,
            state_origin="UNCHANGED",
        )
    for bound in sorted(updates, key=lambda item: item.validated_update.belief_update_id):
        update = bound.validated_update
        proposal = update.proposal
        key = (proposal.person_id, proposal.underlying_id, proposal.proposition_id, proposal.horizon)
        evidence_refs = tuple(sorted({
            item.evidence_id
            for item in bound.supporting_evidence + bound.opposing_evidence
        }))
        prior = current_by_key.get(key)
        result[key] = NextBeliefStateRecord(
            belief_state_id=stable_id("belief-state", update.belief_update_id, update.next_state_version),
            prior_belief_state_id=(
                prior.belief_state_id if isinstance(prior, CurrentBeliefStateRecord) else None
            ),
            belief_update_id=update.belief_update_id,
            person_id=proposal.person_id,
            underlying_id=proposal.underlying_id,
            proposition_id=proposal.proposition_id,
            horizon=proposal.horizon,
            payload=proposal.payload,
            prior_payload=update.delta.prior_payload if update.delta else None,
            delta=update.delta,
            confidence=proposal.confidence,
            uncertainty=proposal.uncertainty,
            evidence_refs=evidence_refs,
            cause_ids=(update.belief_update_id, *evidence_refs),
            updated_at=bound.bound_at,
            state_version=update.next_state_version,
            state_origin="UPDATED",
        )
    return result


def _person_transition(
    *,
    prior: CurrentPersonStateRecord,
    updates: list[EvidenceBoundBeliefUpdateRecord],
    person_policy: PersonSchemaPolicy,
    config: StateChangeConfig,
) -> NextPersonStateRecord:
    updates = sorted(updates, key=lambda item: item.validated_update.belief_update_id)
    transition_at = max((item.bound_at for item in updates), default=prior.updated_at)
    candidate = prior
    changes: list[PersonFieldChange] = []
    belief_update_ids = tuple(item.validated_update.belief_update_id for item in updates)
    evidence_refs = tuple(sorted({
        evidence.evidence_id
        for item in updates
        for evidence in item.supporting_evidence + item.opposing_evidence
    }))

    if updates:
        coverage_quality = fmean(item.evidence_coverage * item.mean_source_quality for item in updates)
        for proposition_id in sorted({item.validated_update.proposal.proposition_id for item in updates}):
            prior_value = candidate.knowledge.get(proposition_id, 0.0)
            change = _clamped_change(
                family="knowledge", field=proposition_id, prior=prior_value,
                target=min(1.0, prior_value + config.knowledge_gain_rate * coverage_quality),
                transition_at=transition_at, prior_updated_at=prior.updated_at,
                policy=person_policy, config=config, reason_code="EVIDENCE_BOUND_BELIEF_UPDATE",
                evidence_refs=evidence_refs, cause_ids=belief_update_ids,
            )
            if change:
                changes.append(change)
                candidate = _replace_map_value(candidate, change.field_path, change.accepted_value)

        alignments = (
            ("attention", "information_focus", config.attention_gain_per_bound_update * len(updates), None, "COGNITIVE_ACTIVATION"),
            ("confidence", "current", config.confidence_alignment_rate, fmean(item.validated_update.proposal.confidence for item in updates), "BELIEF_CONFIDENCE_ALIGNMENT"),
            ("functional_affect", "uncertainty_pressure", config.uncertainty_alignment_rate, fmean(item.validated_update.proposal.uncertainty for item in updates), "BELIEF_UNCERTAINTY_ALIGNMENT"),
        )
        for family, field, rate, observed, reason in alignments:
            prior_value = getattr(candidate, family).get(field, 0.5)
            target = min(1.0, prior_value + rate) if observed is None else prior_value + rate * (observed - prior_value)
            change = _clamped_change(
                family=family, field=field, prior=prior_value, target=target,
                transition_at=transition_at, prior_updated_at=prior.updated_at,
                policy=person_policy, config=config, reason_code=reason,
                evidence_refs=evidence_refs, cause_ids=belief_update_ids,
            )
            if change:
                changes.append(change)
                candidate = _replace_map_value(candidate, change.field_path, change.accepted_value)

    belief_refs = tuple(sorted(set(prior.belief_refs) | set(belief_update_ids)))
    changed = bool(changes or belief_update_ids)
    candidate = candidate.model_copy(update={
        "person_state_id": (
            stable_id("person-state", prior.person_state_id, transition_at.isoformat(), *belief_update_ids)
            if changed else prior.person_state_id
        ),
        "belief_refs": belief_refs,
        "updated_at": transition_at if changed else prior.updated_at,
        "state_version": prior.state_version + 1 if changed else prior.state_version,
    })
    return NextPersonStateRecord(
        transition_id=stable_id("person-transition", prior.person_state_id, transition_at.isoformat(), *belief_update_ids),
        person_id=prior.person_id,
        prior_person_state_id=prior.person_state_id,
        prior_state_version=prior.state_version,
        candidate_state=candidate,
        field_changes=tuple(sorted(changes, key=lambda item: item.field_path)),
        belief_update_ids=belief_update_ids,
        transition_at=transition_at,
        transition_status=TransitionStatus.CANDIDATE if changed else TransitionStatus.NO_CHANGE,
        policy_version=person_policy.policy_version,
        config_version=config.config_version,
    )


def write_person_state_transition(
    *,
    belief_updates: EvidenceBoundBeliefUpdatePanel,
    current_person_states: CurrentPersonStatePanel,
    current_beliefs: CurrentBeliefStatePanel,
    person_policy: PersonSchemaPolicy,
    config: StateChangeConfig,
) -> tuple[NextPersonStatePanel, NextBeliefStatePanel]:
    """Materialize candidate state in separate belief and person transition stages."""

    persons = _unique_by(
        current_person_states.records, lambda item: item.person_id,
        code="DUPLICATE_PERSON_STATE", module_id="P3.S23.M01",
    )
    current_by_key = _unique_by(
        current_beliefs.records, _belief_key,
        code="DUPLICATE_CURRENT_BELIEF", module_id="P3.S23.M01",
    )
    for belief in current_by_key.values():
        if belief.person_id not in persons:
            raise S23InvariantError(
                code="CURRENT_BELIEF_PERSON_NOT_FOUND",
                message=f"current belief references missing person {belief.person_id}",
                module_id="P3.S23.M01",
            )
    committable, by_person = _committable_updates(belief_updates, persons)
    next_beliefs = _next_belief_states(current_by_key, committable)
    transitions = [
        _person_transition(
            prior=prior, updates=by_person.get(person_id, []),
            person_policy=person_policy, config=config,
        )
        for person_id, prior in sorted(persons.items())
        if isinstance(prior, CurrentPersonStateRecord)
    ]
    lineage_sources = tuple(sorted({
        belief_updates.lineage.lineage_id,
        current_person_states.lineage.lineage_id,
        current_beliefs.lineage.lineage_id,
    }))
    person_panel = NextPersonStatePanel(
        status=ArtifactStatus.READY if transitions else ArtifactStatus.EMPTY_VALID,
        records=tuple(transitions),
        lineage=LineageRecord(
            lineage_id=stable_id("lineage-s23-m01-person", *lineage_sources),
            source_artifact_ids=lineage_sources,
            producer_module_id="P3.S23.M01",
        ),
        reason_code="TOOL_PROFICIENCY_PRESERVED_NO_EXECUTION_AUDIT_INPUT",
    )
    belief_panel = NextBeliefStatePanel(
        status=ArtifactStatus.READY if next_beliefs else ArtifactStatus.EMPTY_VALID,
        records=tuple(next_beliefs[key] for key in sorted(next_beliefs)),
        lineage=LineageRecord(
            lineage_id=stable_id("lineage-s23-m01-belief", *lineage_sources),
            source_artifact_ids=lineage_sources,
            producer_module_id="P3.S23.M01",
        ),
    )
    return person_panel, belief_panel

def _state_maps(state: CurrentPersonStateRecord) -> Mapping[str, Mapping[str, float]]:
    return {family: getattr(state, family) for family in _STATE_FAMILIES}


def _path_value(state: CurrentPersonStateRecord, path: str) -> object:
    value: object = state
    for part in path.split("."):
        if hasattr(value, part):
            value = getattr(value, part)
        elif isinstance(value, Mapping) and part in value:
            value = value[part]
        else:
            raise ValueError(f"immutable field path not found: {path}")
    return value


def _actual_numeric_diffs(
    prior: CurrentPersonStateRecord,
    candidate: CurrentPersonStateRecord,
    tolerance: float,
) -> dict[str, tuple[float, float]]:
    result: dict[str, tuple[float, float]] = {}
    prior_maps = _state_maps(prior)
    candidate_maps = _state_maps(candidate)
    for family in _STATE_FAMILIES:
        keys = set(prior_maps[family]) | set(candidate_maps[family])
        for key in keys:
            old = prior_maps[family].get(key, 0.0)
            new = candidate_maps[family].get(key, 0.0)
            if not isclose(old, new, abs_tol=tolerance):
                result[f"{family}.{key}"] = (old, new)
    return result



def _validate_declared_change(
    *,
    path: str,
    old: float,
    new: float,
    declared,
    elapsed: float,
    person_policy: PersonSchemaPolicy,
    config: StateChangeConfig,
) -> list[str]:
    reasons: list[str] = []
    family, _ = path.split(".", 1)
    try:
        speed = person_policy.speed_for(family)
    except ValueError:
        return [f"UNDECLARED_STATE_FAMILY:{family}"]
    change = declared.get(path)
    if change is None:
        return reasons
    allowed = _allowed_delta(speed, elapsed, config)
    if family not in person_policy.transition_authorized_families:
        reasons.append(f"STATE_FAMILY_NOT_AUTHORIZED_IN_S23:{family}")
    if change.speed_class is not speed:
        reasons.append(f"SPEED_CLASS_MISMATCH:{path}")
    if not isclose(change.prior_value, old, abs_tol=config.numeric_tolerance):
        reasons.append(f"PRIOR_VALUE_MISMATCH:{path}")
    if not isclose(change.accepted_value, new, abs_tol=config.numeric_tolerance):
        reasons.append(f"ACCEPTED_VALUE_MISMATCH:{path}")
    if abs(new - old) > allowed + config.numeric_tolerance:
        reasons.append(f"DELTA_CAP_EXCEEDED:{path}")
    if abs(change.allowed_delta - allowed) > config.numeric_tolerance:
        reasons.append(f"ALLOWED_DELTA_MISMATCH:{path}")
    if not change.reason_code:
        reasons.append(f"CHANGE_REASON_MISSING:{path}")
    if family == "tool_proficiency" and config.tool_proficiency_requires_executed_call:
        reasons.append(f"TOOL_PROFICIENCY_CHANGE_REQUIRES_CONTRACTED_AUDIT_INPUT:{path}")
    return reasons


def _validate_transition_identity(
    *, record, prior: CurrentPersonStateRecord, person_policy: PersonSchemaPolicy
) -> list[str]:
    candidate = record.candidate_state
    reasons: list[str] = []
    checks = (
        (record.prior_person_state_id != prior.person_state_id, "PRIOR_STATE_ID_MISMATCH"),
        (record.prior_state_version != prior.state_version, "PRIOR_STATE_VERSION_MISMATCH"),
        (candidate.person_id != prior.person_id, "IMMUTABLE_PERSON_ID_CHANGED"),
        (candidate.profile_hash != prior.profile_hash, "IMMUTABLE_PROFILE_HASH_CHANGED"),
        (candidate.identity != prior.identity, "IMMUTABLE_IDENTITY_CHANGED"),
    )
    reasons.extend(code for failed, code in checks if failed)
    for path in person_policy.immutable_fields:
        try:
            if _path_value(candidate, path) != _path_value(prior, path):
                reasons.append(f"IMMUTABLE_FIELD_CHANGED:{path}")
        except ValueError:
            reasons.append(f"IMMUTABLE_FIELD_PATH_INVALID:{path}")
    return reasons


def _validate_transition_causality(record, prior: CurrentPersonStateRecord) -> list[str]:
    candidate = record.candidate_state
    reasons: list[str] = []
    if record.transition_status is TransitionStatus.NO_CHANGE:
        if candidate.state_version != prior.state_version:
            reasons.append("NO_CHANGE_VERSION_MUST_REMAIN")
        if candidate.belief_refs != prior.belief_refs:
            reasons.append("NO_CHANGE_BELIEF_REFS_CHANGED")
        return reasons
    if candidate.state_version != prior.state_version + 1:
        reasons.append("CANDIDATE_VERSION_MUST_INCREMENT_ONCE")
    if not record.belief_update_ids and not record.field_changes:
        reasons.append("CANDIDATE_HAS_NO_CAUSE")
    if not set(prior.belief_refs).issubset(candidate.belief_refs):
        reasons.append("BELIEF_REFS_REMOVED")
    if not set(record.belief_update_ids).issubset(candidate.belief_refs):
        reasons.append("BELIEF_UPDATE_REFS_NOT_PERSISTED")
    return reasons


def _transition_reasons(
    *,
    record,
    prior: CurrentPersonStateRecord | None,
    person_policy: PersonSchemaPolicy,
    config: StateChangeConfig,
) -> list[str]:
    if prior is None:
        return ["PRIOR_PERSON_STATE_NOT_FOUND"]
    reasons = _validate_transition_identity(record=record, prior=prior, person_policy=person_policy)
    actual = _actual_numeric_diffs(prior, record.candidate_state, config.numeric_tolerance)
    declared = {change.field_path: change for change in record.field_changes}
    if set(actual) != set(declared):
        reasons.append("DECLARED_CHANGE_SET_MISMATCH")
    elapsed = _elapsed_days(prior.updated_at, record.transition_at, module_id="P3.S23.M02")
    for path, (old, new) in actual.items():
        reasons.extend(_validate_declared_change(
            path=path, old=old, new=new, declared=declared, elapsed=elapsed,
            person_policy=person_policy, config=config,
        ))
    reasons.extend(_validate_transition_causality(record, prior))
    return reasons


def guard_gradual_changes(
    *,
    candidates: NextPersonStatePanel,
    current_states: CurrentPersonStatePanel,
    person_policy: PersonSchemaPolicy,
    config: StateChangeConfig,
) -> ValidatedNextPersonStatePanel:
    current = _unique_by(
        current_states.records,
        lambda item: item.person_id,
        code="DUPLICATE_PERSON_STATE",
        module_id="P3.S23.M02",
    )
    accepted: list[CurrentPersonStateRecord] = []
    rejections: list[RejectedPersonStateTransition] = []
    flags: list[bool] = []
    seen: set[str] = set()
    for record in sorted(candidates.records, key=lambda item: item.person_id):
        reasons = ["DUPLICATE_CANDIDATE_PERSON"] if record.person_id in seen else []
        seen.add(record.person_id)
        prior_obj = current.get(record.person_id)
        prior = prior_obj if isinstance(prior_obj, CurrentPersonStateRecord) else None
        reasons.extend(_transition_reasons(
            record=record, prior=prior, person_policy=person_policy, config=config
        ))
        ok = not reasons
        flags.append(ok)
        if ok:
            accepted.append(record.candidate_state)
        else:
            rejections.append(RejectedPersonStateTransition(
                transition_id=record.transition_id,
                person_id=record.person_id,
                reason_codes=tuple(sorted(set(reasons))),
            ))
    lineage_sources = tuple(sorted({candidates.lineage.lineage_id, current_states.lineage.lineage_id}))
    return ValidatedNextPersonStatePanel(
        status=_panel_status(flags, empty=not candidates.records),
        records=tuple(accepted),
        rejections=tuple(rejections),
        lineage=LineageRecord(
            lineage_id=stable_id("lineage-s23-m02", *lineage_sources),
            source_artifact_ids=lineage_sources,
            producer_module_id="P3.S23.M02",
        ),
        reason_code=None if all(flags) else "ONE_OR_MORE_STATE_TRANSITIONS_REJECTED",
    )
